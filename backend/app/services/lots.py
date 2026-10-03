"""LÔ HÀNG — chuỗi khối lượng từ vườn tới lô xuất khẩu, và CHỨNG THƯ LÔ HÀNG.

LỖ HỔNG LỚN NHẤT CỦA TRUY XUẤT BẰNG GIẤY là "rửa hàng": cà phê từ vùng mới phá
rừng được khai là của một vườn sạch có hồ sơ đẹp. Hồ sơ vườn có thật, chỉ có khối
lượng là bịa. Chặn bằng CÂN BẰNG KHỐI LƯỢNG: tổng số kg MỌI lô (của MỌI doanh nghiệp
trên TerraTwin) khai từ một vườn trong một vụ không được vượt
    diện tích ranh đo × năng suất trần của cây đó.
Năng suất trần đặt RỘNG có chủ ý (gấp ~2 lần bình quân cả nước) để không chặn nhầm
vườn thâm canh tốt — vượt trần nghĩa là thửa đó KHÔNG THỂ làm ra chừng ấy hàng.

CHỨNG THƯ LÔ HÀNG: gốc Merkle (RFC 6962) của các đợt nhập — mỗi lá là
    {"dossier_id", "entry_hash", "kg"}  (JSON chuẩn hoá)
— được phát hành như một hồ sơ trong sổ móc xích (ký Ed25519, vào sổ minh bạch).
Nội dung CÔNG KHAI không chứa danh sách nhà cung cấp (bí mật kinh doanh, dữ liệu
nông hộ): chỉ gốc, số vườn, tổng khối lượng, kết quả kiểm. Mỗi vườn nhận BẰNG CHỨNG
THUỘC LÔ (⌈log₂ n⌉ mã băm) để tự chứng minh "hàng của tôi nằm trong lô này" với ngân
hàng, nhà nhập khẩu, mà không lộ các vườn khác.
"""
from __future__ import annotations

import json
import secrets
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Dossier, DossierMonitor, Lot
from app.services import dossier, eudr, merkle
from app.services.reqlang import tr

SCHEMA = "terratwin.lot/1"
# Năng suất TRẦN (tấn/ha/năm) — rộng có chủ ý. Bình quân Việt Nam để so: cà phê
# nhân ~2,7–3 t/ha, cao su khô ~1,7 t/ha, ca cao hạt ~1 t/ha.
YIELD_CAP_T_HA = {"coffee": 6.0, "rubber": 3.5, "cocoa": 2.5}
YIELD_WARN_T_HA = {"coffee": 4.5, "rubber": 2.5, "cocoa": 1.8}
HS = {
    "coffee": ("0901", "Cà phê (Coffee)"), "rubber": ("4001", "Cao su tự nhiên (Natural rubber)"),
    "cocoa": ("1801", "Hạt ca cao (Cocoa beans)"), "wood": ("44", "Gỗ và sản phẩm gỗ (Wood)"),
    "other": ("", ""),
}
_ID = "abcdefghijkmnpqrstuvwxyz23456789"


def new_id() -> str:
    return "".join(secrets.choice(_ID) for _ in range(12))


def leaf_data(d: dict) -> bytes:
    return json.dumps({"dossier_id": d["dossier_id"], "entry_hash": d["entry_hash"], "kg": d["kg"]},
                      sort_keys=True, separators=(",", ":")).encode("utf-8")


def _leaves(dels: list[dict]) -> list[bytes]:
    return [merkle.leaf_hash(leaf_data(d)) for d in sorted(dels, key=lambda d: d["dossier_id"])]


def normalize(rows: list[dict]) -> tuple[list[dict], list[str]]:
    """Gộp trùng mã hồ sơ (cộng kg), bỏ dòng hỏng. → (đợt nhập, lỗi)."""
    out: dict[str, dict] = {}
    errs = []
    for i, r in enumerate(rows, 1):
        did = str(r.get("dossier_id") or "").strip().lower()
        try:
            kg = float(r.get("kg"))
        except (TypeError, ValueError):
            kg = -1
        if not did or kg <= 0:
            errs.append(tr(f"Dòng {i}: cần mã hồ sơ và số kg > 0.", f"Row {i}: a dossier ID and kg > 0 are required."))
            continue
        cur = out.setdefault(did, {"dossier_id": did, "kg": 0.0, "date": r.get("date") or None,
                                   "review_ack": None})
        cur["kg"] = round(cur["kg"] + kg, 3)
        if r.get("review_ack"):
            cur["review_ack"] = str(r["review_ack"])[:300]
    return list(out.values()), errs


def _monitor_changed(db: Session, did: str) -> bool:
    m = db.execute(select(DossierMonitor).where(DossierMonitor.dossier_id == did)
                   .order_by(DossierMonitor.checked_at.desc()).limit(1)).scalars().first()
    return bool(m and m.changed)


def other_kg(db: Session, did: str, season: str, exclude_lot: str | None) -> float:
    """kg vườn này đã khai trong MỌI lô khác cùng vụ — kể cả của doanh nghiệp khác:
    một vườn bán cho hai nơi vẫn chỉ có một sức sản xuất."""
    total = 0.0
    for lot in db.execute(select(Lot).where(Lot.season == season)).scalars().all():
        if lot.id == exclude_lot:
            continue
        for d in json.loads(lot.deliveries_json or "[]"):
            if d.get("dossier_id") == did:
                total += float(d.get("kg") or 0)
    return total


def check(db: Session, lot: Lot) -> dict:
    """Kiểm từng đợt nhập + cân bằng khối lượng. Ghi lại vào lot.checks_json."""
    dels = json.loads(lot.deliveries_json or "[]")
    rows, area, kg_total = [], 0.0, 0.0
    by_level: dict[str, int] = {}
    for d in dels:
        did = d["dossier_id"]
        row = db.get(Dossier, did)
        r = {"dossier_id": did, "kg": d["kg"], "status": "ok", "notes": []}

        def block(msg):
            r["status"] = "blocked"
            r["notes"].append(msg)

        def warn(msg):
            if r["status"] == "ok":
                r["status"] = "warning"
            r["notes"].append(msg)
        if row is None:
            block(tr("Không có hồ sơ mang mã này.", "No dossier with this ID."))
            rows.append(r)
            continue
        f = json.loads(row.facts_json)
        if f.get("kind") != "eudr_plot":
            block(tr("Không phải Hồ sơ vườn chuẩn EUDR.", "Not an EUDR plot dossier."))
            rows.append(r)
            continue
        d["entry_hash"] = row.entry_hash
        plot, scr = f["plot"], f.get("screening") or {}
        r.update(ref=plot.get("ref"), area_ha=plot.get("area_ha"), level=scr.get("level"),
                 issued_at=row.created_at.date().isoformat())
        area += float(plot.get("area_ha") or 0)
        kg_total += d["kg"]
        by_level[scr.get("level") or "unknown"] = by_level.get(scr.get("level") or "unknown", 0) + 1
        if not dossier.verify_row(db, row)["valid"]:
            block(tr("Hồ sơ KHÔNG qua kiểm chứng chữ ký / sổ móc xích.", "Dossier FAILED signature / chain verification."))
        lv = scr.get("level")
        if lv in ("high", "unknown"):
            block(tr(f"Sàng lọc: {scr.get('label')} — không được đưa vào lô.",
                     f"Screening: {scr.get('label')} — cannot enter the lot."))
        elif lv == "review":
            if d.get("review_ack"):
                warn(tr(f"Cần xem lại — đã xác nhận: “{d['review_ack']}”.",
                        f"Needs review — acknowledged: “{d['review_ack']}”."))
            else:
                block(tr("Sàng lọc “Cần xem lại”: phải ghi lý do đã xem xét (ảnh thực địa, giấy tờ) mới được vào lô.",
                         "Screening “Needs review”: record why it was cleared (field photos, documents) before it can enter."))
        if _monitor_changed(db, did):
            block(tr("Giám sát sau phát hành phát hiện thay đổi — sàng lọc lại trước khi bán.",
                     "Post-issuance monitoring found a change — re-screen before selling."))
        if plot.get("commodity") and lot.commodity and plot["commodity"] != lot.commodity:
            warn(tr(f"Hồ sơ khai nông sản “{plot.get('commodity_label')}”, lô là “{eudr.commodity_label(lot.commodity)}”.",
                    f"Dossier declares “{plot.get('commodity_label')}”, the lot is “{eudr.commodity_label(lot.commodity)}”."))
        cap = YIELD_CAP_T_HA.get(lot.commodity)
        if cap and plot.get("area_ha"):
            prior = other_kg(db, did, lot.season, lot.id)
            used = prior + d["kg"]
            cap_kg = float(plot["area_ha"]) * cap * 1000
            warn_kg = float(plot["area_ha"]) * YIELD_WARN_T_HA[lot.commodity] * 1000
            r.update(cap_kg=round(cap_kg), season_kg=round(used, 1), other_lots_kg=round(prior, 1))
            if used > cap_kg:
                block(tr(f"Vượt năng suất trần: vụ {lot.season} đã khai {used:,.0f} kg từ {plot['area_ha']} ha "
                         f"(trần {cap} t/ha = {cap_kg:,.0f} kg) — vườn này không thể làm ra chừng ấy hàng.",
                         f"Above the yield cap: {used:,.0f} kg declared from {plot['area_ha']} ha in {lot.season} "
                         f"(cap {cap} t/ha = {cap_kg:,.0f} kg) — this plot cannot produce that much."))
            elif used > warn_kg:
                warn(tr(f"Năng suất cao bất thường: {used / float(plot['area_ha']) / 1000:.1f} t/ha (bình quân VN ~2,7–3).",
                        f"Unusually high yield: {used / float(plot['area_ha']) / 1000:.1f} t/ha (VN average ~2.7–3)."))
        try:
            if d.get("date") and date.fromisoformat(d["date"]) < row.created_at.date():
                warn(tr("Ngày nhập hàng TRƯỚC ngày phát hành hồ sơ vườn.", "Delivery date is BEFORE the plot dossier was issued."))
        except ValueError:
            pass
        rows.append(r)
    lot.deliveries_json = json.dumps(dels, ensure_ascii=False)
    n_block = sum(1 for r in rows if r["status"] == "blocked")
    out = {
        "rows": rows, "n": len(rows), "n_blocked": n_block,
        "n_warning": sum(1 for r in rows if r["status"] == "warning"),
        "quantity_kg": round(kg_total, 1), "area_ha": round(area, 4), "by_level": by_level,
        "certifiable": bool(rows) and n_block == 0,
        "headline": (tr(f"{len(rows)} vườn, {kg_total:,.0f} kg — đủ điều kiện phát hành chứng thư lô hàng.",
                        f"{len(rows)} plots, {kg_total:,.0f} kg — eligible for a lot certificate.")
                     if rows and n_block == 0 else
                     tr(f"{n_block}/{len(rows)} đợt nhập bị chặn — sửa trước khi phát hành chứng thư.",
                        f"{n_block}/{len(rows)} deliveries are blocked — fix them before certifying.")),
    }
    lot.checks_json = json.dumps(out, ensure_ascii=False)
    return out


def certificate_facts(lot: Lot, chk: dict) -> dict:
    from app.services import reqlang

    dels = [d for d in json.loads(lot.deliveries_json) if d.get("entry_hash")]
    leaves = _leaves(dels)
    hs, hs_desc = HS.get(lot.commodity, HS["other"])
    return {
        "schema": SCHEMA, "kind": "lot_certificate", "lang": reqlang.cur_lang(),
        "lot": {"ref": lot.ref, "commodity": lot.commodity, "commodity_label": eudr.commodity_label(lot.commodity),
                "hs_code": hs, "hs_description": hs_desc, "season": lot.season, "operator": lot.operator,
                "quantity_kg": chk["quantity_kg"], "n_plots": len(dels), "area_ha": chk["area_ha"],
                "country_of_production": "VN"},
        "merkle": {"algorithm": "RFC 6962 SHA-256", "root": merkle.root(leaves).hex(), "size": len(leaves),
                   "leaf": 'leaf_hash(JSON chuẩn hoá {"dossier_id","entry_hash","kg"}), sắp theo dossier_id'},
        "mass_balance": {"yield_cap_t_ha": YIELD_CAP_T_HA.get(lot.commodity),
                         "rule": tr("Tổng kg mọi lô cùng vụ từ một vườn ≤ diện tích ranh đo × năng suất trần.",
                                    "Total kg across all lots in a season from one plot ≤ measured area × yield cap.")},
        "checks": {"by_level": chk["by_level"], "n_warning": chk["n_warning"], "n_blocked": chk["n_blocked"]},
        "evidence_classes": {"lot.quantity_kg": "declared", "merkle": "derived", "checks": "derived"},
        "predictions_included": False,
        "disclaimer": tr(
            "Chứng thư xác nhận các đợt nhập trên khớp các Hồ sơ vườn đã ký và qua kiểm cân bằng khối lượng tại "
            "thời điểm phát hành. Khối lượng do doanh nghiệp khai. Không phải chứng nhận tuân thủ EUDR.",
            "Certifies that the deliveries match signed plot dossiers and passed the mass-balance check at "
            "issuance. Quantities are declared by the operator. Not EUDR compliance certification."),
    }


def proof_for(lot: Lot, dossier_id: str) -> dict | None:
    dels = sorted([d for d in json.loads(lot.deliveries_json) if d.get("entry_hash")], key=lambda d: d["dossier_id"])
    idx = next((i for i, d in enumerate(dels) if d["dossier_id"] == dossier_id), None)
    if idx is None:
        return None
    leaves = _leaves(dels)
    d = dels[idx]
    # leaf_data: ĐÚNG chuỗi đã băm — JavaScript viết 4000.0 thành 4000, nên người kiểm phải băm chuỗi này
    # (và đối chiếu nó với các trường), không tự dựng lại JSON.
    return {"lot_certificate": lot.certificate_id, "leaf": {"dossier_id": d["dossier_id"], "entry_hash": d["entry_hash"],
                                                            "kg": d["kg"]},
            "leaf_data": leaf_data(d).decode("utf-8"),
            "leaf_index": idx, "tree_size": len(leaves), "root": merkle.root(leaves).hex(),
            "proof": merkle.hexes(merkle.inclusion_proof(idx, leaves))}


def dds(db: Session, lot: Lot) -> dict:
    """Bản NHÁP tờ khai thẩm định (DDS) — sinh TẤT ĐỊNH từ dữ liệu, không để AI điền số."""
    from app.services import eudr_geo

    dels = json.loads(lot.deliveries_json or "[]")
    feats, refs, dates = [], [], []
    for d in dels:
        row = db.get(Dossier, d["dossier_id"])
        if row is None:
            continue
        f = json.loads(row.facts_json)
        p = f.get("plot") or {}
        props = {"ProducerCountry": "VN", "ProductionPlace": p.get("ref")}
        if p.get("producer"):
            props["ProducerName"] = p["producer"]
        if p.get("kind") == "point" and p.get("area_source") == "declared":
            props["Area"] = p.get("area_ha")
        feats.append({"type": "Feature", "properties": props, "geometry": p.get("geometry")})
        refs.append({"dossier_id": d["dossier_id"], "kg": d["kg"],
                     "screening": (f.get("screening") or {}).get("level")})
        if d.get("date"):
            dates.append(d["date"])
    hs, hs_desc = HS.get(lot.commodity, HS["other"])
    return {
        "draft": True,
        "note": tr("BẢN NHÁP để doanh nghiệp đối chiếu rồi tự nhập vào hệ thống thông tin EUDR (TRACES). Người nộp chịu "
                   "trách nhiệm về tờ khai.",
                   "DRAFT for the operator to check and enter into the EUDR information system (TRACES) themselves. The "
                   "filer is responsible for the statement."),
        "operator": {"name": lot.operator or None, "eori": None, "address": None},
        "activity": "export",
        "commodity": {"hs_code": hs, "description": hs_desc, "net_mass_kg": round(sum(d["kg"] for d in dels), 1)},
        "country_of_production": "VN",
        "production_period": {"season": lot.season, "first_delivery": min(dates) if dates else None,
                              "last_delivery": max(dates) if dates else None},
        "geolocation": {"type": "FeatureCollection", "features": feats},
        "geolocation_valid": all(eudr_geo.validate_geometry(ft["geometry"])["valid"] for ft in feats if ft["geometry"]),
        "supporting_evidence": {"terratwin_lot_certificate": lot.certificate_id, "plot_dossiers": refs},
        "assertions": {"deforestation_free": tr("Mọi vườn trong lô đạt sàng lọc TerraTwin (hoặc đã ghi lý do xem xét).",
                                                "Every plot passed TerraTwin screening (or has a recorded review)."),
                       "legality": tr("Doanh nghiệp tự xác nhận tính hợp pháp theo luật Việt Nam; xem giấy tờ đất "
                                      "đính kèm từng hồ sơ nếu có.",
                                      "The operator confirms legality under Vietnamese law; see land documents "
                                      "attached to each dossier where present.")},
    }

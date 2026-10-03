"""HỒ SƠ VƯỜN CHUẨN EUDR — ghép ranh thửa (eudr_geo) + sàng lọc phá rừng
(eudr_forest) thành: lô thửa chạy nền, báo cáo CSV, tệp GeoJSON nộp EU, và Hồ sơ
đất số ký số cho TỪNG vườn.

QUY TẮC TIN CẬY. Mọi mục trong hồ sơ EUDR mang nhãn:
  measured — đo trực tiếp (ranh do người khai đo; tỉ lệ rừng từ bản đồ vệ tinh)
  derived  — tính lại được từ số đo bằng quy tắc công khai (chuẩn EU, kết luận)
KHÔNG có mục "dự đoán" nào: hồ sơ dùng để quyết định chuyện tiền bạc, mua bán.

HỒ SƠ THUỘC VỀ NÔNG HỘ. Mã hồ sơ + QR in ra giấy được; ai cầm cũng tự kiểm ở
/h/<mã> mà không cần tài khoản, không cần tin TerraTwin (chữ ký Ed25519 + sổ móc
xích, xem dossier.py). Đem bán cho đại lý nào cũng được.
"""
from __future__ import annotations

import csv
import io
import json
import os

from app.services import eudr_forest, eudr_geo
from app.services.reqlang import tr

FACTS_SCHEMA = "terratwin.eudr-plot/1"
COMMODITIES = {
    "coffee": ("Cà phê", "Coffee"), "rubber": ("Cao su", "Rubber"), "wood": ("Gỗ", "Wood"),
    "cocoa": ("Ca cao", "Cocoa"), "other": ("Khác", "Other"),
}
JOB_KIND = "eudr_screen"


def _env_num(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def max_screen() -> int:
    """Trần số thửa SÀNG LỌC mỗi lô (mỗi thửa ~15 lượt gọi Planetary Computer)."""
    return int(_env_num("TERRATWIN_EUDR_MAX_PLOTS", 100))


def commodity_label(c: str | None) -> str:
    vi, en = COMMODITIES.get(c or "", COMMODITIES["other"])
    return tr(vi, en)


# ------------------------------------------------------------------ tổng hợp lô

def summarize(plots: list[dict], results: dict) -> dict:
    by_level = {k: 0 for k in eudr_forest.LEVELS}
    ha = {k: 0.0 for k in eudr_forest.LEVELS}
    for p in plots:
        r = results.get(str(p["index"]))
        if not r:
            continue
        lv = r.get("level") or "unknown"
        by_level[lv] = by_level.get(lv, 0) + 1
        ha[lv] = ha.get(lv, 0.0) + float(p.get("area_ha") or 0)
    n_valid = sum(1 for p in plots if p["valid"])
    n_screened = sum(by_level.values())
    flagged = by_level["high"] + by_level["review"]
    return {
        "n": len(plots), "n_valid": n_valid, "n_invalid": len(plots) - n_valid,
        "n_screened": n_screened, "by_level": by_level,
        "ha_by_level": {k: round(v, 2) for k, v in ha.items()},
        "headline": (tr(f"{by_level['low']}/{n_screened} thửa đạt sàng lọc; {by_level['high']} rủi ro phá rừng, "
                        f"{by_level['review']} cần xem lại"
                        + (f"; {len(plots) - n_valid} thửa lỗi chuẩn EU chưa sàng lọc" if len(plots) > n_valid else "")
                        + ".",
                        f"{by_level['low']}/{n_screened} plots passed screening; {by_level['high']} deforestation "
                        f"risk, {by_level['review']} need review"
                        + (f"; {len(plots) - n_valid} with EU format errors not screened" if len(plots) > n_valid
                           else "") + ".")
                     if n_screened else tr("Chưa sàng lọc được thửa nào.", "No plot screened yet.")),
        "flagged": flagged,
    }


# ------------------------------------------------------------------ xuất tệp

def export_geojson(plots: list[dict], results: dict, which: str = "valid",
                   producer: str | None = None) -> dict:
    """which: valid — mọi thửa đúng chuẩn EU · passed — chỉ thửa đạt sàng lọc."""
    keep = []
    for p in plots:
        if not p["valid"]:
            continue
        if which == "passed" and (results.get(str(p["index"])) or {}).get("level") != "low":
            continue
        keep.append(p)
    return eudr_geo.to_eu_geojson(keep, producer_name=producer or None)


CSV_COLUMNS = ["ref", "producer", "kind", "area_ha", "area_source", "lat", "lon", "eu_valid", "eu_issues",
               "level", "label", "wc2020_forest_pct", "alos2020_forest_pct", "io2018_2020_tree_pct",
               "io2022_2023_tree_pct", "ndvi_before", "ndvi_after", "protected_area", "reasons", "dossier_url"]


def to_csv(plots: list[dict], results: dict, base_url: str = "") -> str:
    from app.services.batch import _cell

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLUMNS)
    for p in plots:
        r = results.get(str(p["index"])) or {}
        maps = {f["id"]: f.get("pct") for f in r.get("forest_2020") or []}
        s2 = r.get("s2") or {}
        sig = r.get("signals") or {}
        c = p.get("centroid") or {}
        w.writerow([_cell(x) for x in (
            p.get("ref"), p.get("producer"), p.get("kind"), p.get("area_ha"), p.get("area_source"),
            c.get("lat"), c.get("lon"), "yes" if p["valid"] else "no",
            " | ".join(f"[{i['level']}] {i['message']}" for i in p.get("issues") or []),
            r.get("level"), r.get("label"), maps.get("wc2020"), maps.get("alos2020"), maps.get("io"),
            sig.get("io_after_pct"), (s2.get("before") or {}).get("ndvi_mean"),
            (s2.get("after") or {}).get("ndvi_mean"),
            ", ".join((r.get("protected") or {}).get("inside") or []),
            " ".join(r.get("reasons") or []),
            f"{base_url}/h/{r['dossier_id']}" if r.get("dossier_id") else "")])
    return "﻿" + buf.getvalue()


# ------------------------------------------------------------------ hồ sơ ký số

def dossier_facts(plot: dict, screening: dict, commodity: str | None = None,
                  producer: str | None = None) -> dict:
    """Nội dung Hồ sơ vườn chuẩn EUDR — chỉ số ĐO và số TÍNH LẠI ĐƯỢC."""
    from app.services import reqlang

    eu_issues = [{"code": i["code"], "level": i["level"], "message": i["message"]}
                 for i in plot.get("issues") or []]
    return {
        "schema": FACTS_SCHEMA,
        "kind": "eudr_plot",
        "lang": reqlang.cur_lang(),
        "plot": {
            "ref": plot.get("ref"), "producer": producer or plot.get("producer"),
            "country": (plot.get("country") or "VN"), "commodity": commodity or None,
            "commodity_label": commodity_label(commodity) if commodity else None,
            "kind": plot.get("kind"), "geometry": plot.get("geometry"),
            "area_ha": plot.get("area_ha"), "area_source": plot.get("area_source"),
            "centroid": plot.get("centroid"), "n_vertices": plot.get("n_vertices"),
        },
        "eu_format": {"valid": bool(plot.get("valid")), "issues": eu_issues,
                      "rules": tr("Quy định (EU) 2023/1115 Điều 2(28), 9(1)(d); mô tả tệp GeoJSON của TRACES.",
                                  "Regulation (EU) 2023/1115 Art. 2(28), 9(1)(d); TRACES GeoJSON file description.")},
        "screening": screening,
        "evidence_classes": {
            "plot.geometry": "measured", "eu_format": "derived",
            "screening.forest_2020": "measured", "screening.io_trajectory": "measured",
            "screening.s2": "measured", "screening.level": "derived",
        },
        "predictions_included": False,
        "sources": eudr_forest.sources(),
        "reproduce": tr(
            "Mọi tỉ lệ rừng là thống kê lớp trên đúng ranh thửa này, tính trên các tấm bản đồ ghi trong "
            "'items' qua API công khai của Microsoft Planetary Computer (/api/data/v1/item/statistics, "
            "categorical=true). Kết luận áp quy tắc công khai terratwin.eudr-screen/1 lên các con số đó — ai "
            "cũng tự tính lại được.",
            "Every forest share is a class statistic over exactly this boundary, on the map tiles listed in "
            "'items', via Microsoft Planetary Computer's public API (/api/data/v1/item/statistics, "
            "categorical=true). The conclusion applies the public rule terratwin.eudr-screen/1 to those "
            "numbers — anyone can recompute it."),
        "disclaimer": tr(
            "Hồ sơ SÀNG LỌC theo dữ liệu vệ tinh công khai tại thời điểm phát hành — không phải chứng nhận tuân "
            "thủ EUDR, không thay thế giấy chứng nhận quyền sử dụng đất hay kiểm tra thực địa. Ranh thửa do "
            "người khai đo; TerraTwin không xác nhận quyền sử dụng đất.",
            "A SCREENING dossier from public satellite data at issuance — not EUDR compliance certification, "
            "and it does not replace land-use right certificates or field checks. The boundary was measured by "
            "the declarant; TerraTwin does not confirm land rights."),
    }


# ------------------------------------------------------------------ việc nền

def _register() -> None:
    import time

    from app.services import jobs_db, reqlang

    @jobs_db.register(JOB_KIND)
    def _job(args: dict) -> dict:
        from sqlalchemy import select

        from app import db as _db
        from app.db import EudrSet

        reqlang.set_lang(args.get("lang"))
        job_id = args.get("_job_id")

        def _still_there(s) -> bool:
            return s.execute(select(EudrSet.id).where(EudrSet.id == job_id)).first() is not None

        with _db.SessionLocal() as s:
            row = s.get(EudrSet, job_id)
            if row is None:
                return {"set_id": job_id, "cancelled": True}
            plots = json.loads(row.plots_json or "[]")
            results = json.loads(row.results_json or "{}")         # chạy TIẾP từ thửa dở
            todo = [p for p in plots if p["valid"] and str(p["index"]) not in results][
                :max(0, max_screen() - len(results))]
            row.state = "running"
            s.commit()
            total = len(results) + len(todo)

            def report(cur: str) -> None:
                jobs_db.report_progress(job_id, {"done": len(results), "total": total, "current": cur,
                                                 "phase": "running"})

            for k, p in enumerate(todo):
                report(p["ref"])
                try:
                    r = eudr_forest.screen(p)
                except Exception:
                    r = {"level": "unknown", "label": eudr_forest.label("unknown"),
                         "reasons": [tr("Lỗi khi sàng lọc thửa này.", "Error screening this plot.")],
                         "forest_2020": [], "io_trajectory": []}
                results[str(p["index"])] = r
                if not _still_there(s):                    # người dùng đã xoá lô
                    return {"set_id": job_id, "cancelled": True}
                row.results_json = json.dumps(results, ensure_ascii=False)
                s.commit()
                if k < len(todo) - 1:
                    time.sleep(_env_num("TERRATWIN_EUDR_DELAY_S", 1))
            summary = summarize(plots, results)
            row.summary_json = json.dumps(summary, ensure_ascii=False)
            row.state = "done"
            s.commit()
        jobs_db.report_progress(job_id, {"done": len(results), "total": total, "current": "", "phase": "done"})
        return {"set_id": job_id, "summary": summary}


_register()

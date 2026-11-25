"""Nâng cấp 25/11/2026 — từ điển địa danh nội bộ: gõ không dấu / sai chính tả, và tìm được khi dịch vụ ngoài sập."""
from __future__ import annotations

from app.services import gazetteer as g, place


def test_thuat_toan_chuoi():
    assert g.levenshtein("quang dien", "quang dienn") == 1 and g.levenshtein("abc", "xyz", cap=1) == 2
    assert g.jaro_winkler("dong thap", "dong thap") == 1.0
    assert g.jaro_winkler("martha", "marhta") > 0.95 > g.jaro_winkler("abc", "xyz")
    t = g.Trie()
    for i, w in enumerate(["quang dien", "quang yen", "hai phong"]):
        t.add(w, i)
    assert t.prefix("quang") == [0, 1] and t.prefix("hai p") == [2] and t.prefix("zz") == []


def test_go_khong_dau_va_sai_chinh_ta():
    assert g.suggest("quang dienn")[0]["label"] == "Quang Dien · Thừa Thiên Huế"
    assert g.suggest("hai phongg")[0]["label"] == "Hải Phòng"
    assert g.suggest("qang ngai")[0]["label"].startswith("Quảng Ngãi") or g.suggest("qang ngai")[0]["label"].startswith("Quang Ngai")
    r = g.suggest("Phong Dien, Hue")
    assert r and all("Huế" in x["label"] for x in r)
    q = g.suggest("Ba Tri")[0]
    assert q["label"] == "Ba Tri · Bến Tre" and 9.9 < q["lat"] < 10.3 and 106.4 < q["lon"] < 106.8   # điểm nằm trong huyện
    assert g.suggest("x") == [] and g.suggest("zzqqxx") == []


def test_tim_khi_ca_ba_dich_vu_sap(monkeypatch):
    monkeypatch.setattr(place, "_SOURCES", (lambda q: None, lambda q: None, lambda q: None))
    monkeypatch.setattr(place.cache_store, "get", lambda k: None)
    r = place.search("quang dienn")
    assert r["results"][0]["source"] == "local-gazetteer" and "không phản hồi" in r["message"]


def test_dich_vu_ngoai_co_ket_qua_thi_uu_tien(monkeypatch):
    hit = [{"label": "Tuệ Tĩnh · Hải Phòng", "lat": 20.97, "lon": 106.28, "kind": "", "source": "open-meteo"}]
    monkeypatch.setattr(place, "_SOURCES", (lambda q: hit,))
    monkeypatch.setattr(place.cache_store, "get", lambda k: None)
    monkeypatch.setattr(place.cache_store, "put", lambda *a, **k: None)
    assert place.search("tue tinh")["results"] == hit

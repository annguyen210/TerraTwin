"""AlphaEarth: bộ đọc GeoZarr (shard giả, không mạng), giải lượng tử, mô hình, API trạng thái/dự đoán."""
from __future__ import annotations

import json
import re
import struct

import numpy as np
import pytest
import zstandard


def _fake_shard(chunks: dict[tuple[int, int], np.ndarray]) -> bytes:
    """Một shard Zarr v3 'sharding_indexed' tối thiểu: khối con zstd nối nhau + bảng chỉ mục ở cuối."""
    from app.services import aef
    body, index = b"", []
    for iy in range(aef.PER):
        for ix in range(aef.PER):
            if (iy, ix) in chunks:
                raw = zstandard.ZstdCompressor(level=3).compress(chunks[(iy, ix)].astype("<i1").tobytes())
                index.append((len(body), len(raw)))
                body += raw
            else:
                index.append((aef._MISSING, aef._MISSING))
    idx = b"".join(struct.pack("<QQ", o, n) for o, n in index)
    return body + idx + b"\x00\x00\x00\x00"           # + crc32c (bộ đọc không cần kiểm)


@pytest.fixture
def fake_store(monkeypatch):
    from app.services import aef
    aef.clear_cache()
    store: dict[str, bytes] = {}

    def fake_get(url, rng=None, timeout=0, tries=0):
        if url not in store:
            import urllib.error
            raise urllib.error.HTTPError(url, 404, "nf", {}, None)
        data = store[url]
        m = re.match(r"bytes=-(\d+)$", rng or "")
        if m:
            return data[-int(m.group(1)):]
        a, b = map(int, re.match(r"bytes=(\d+)-(\d+)$", rng).groups())
        return data[a:b + 1]
    monkeypatch.setattr(aef, "_get", fake_get)
    yield store
    aef.clear_cache()


def test_doc_dung_vecto_tai_diem_va_bo_o_trong(fake_store):
    from app.services import aef
    lat, lon = 12.68, 108.05
    r, c = aef.pixel(lat, lon)
    sy, sx, iy, ix = r // aef.SHARD, c // aef.SHARD, (r % aef.SHARD) // aef.INNER, (c % aef.SHARD) // aef.INNER
    ch = np.full((64, aef.INNER, aef.INNER), aef.NODATA, "<i1")
    vec = np.array([60] * 32 + [-60] * 32, "<i1")
    ch[:, r % aef.INNER, c % aef.INNER] = vec
    fake_store[aef._shard_url(aef.YEARS.index(2020), sy, sx)] = _fake_shard({(iy, ix): ch})

    v, n = aef.around(lat, lon, 2020, half_px=0)
    assert n == 1 and abs(float(np.linalg.norm(v)) - 1) < 1e-6
    expect = aef.dequantize(vec)
    assert np.allclose(v, expect / np.linalg.norm(expect))
    # ô xung quanh là -128 (trống) → bị bỏ, vẫn chỉ 1 điểm ảnh hợp lệ
    v2, n2 = aef.around(lat, lon, 2020, half_px=2)
    assert n2 == 1 and np.allclose(v2, v)
    # năm khác không có shard → None, không ném lỗi
    assert aef.around(lat, lon, 2021, half_px=0) == (None, 0)


def test_giai_luong_tu_dung_cong_thuc_tai_lieu():
    from app.services import aef
    x = np.array([127, -127, 0, 64], "<i1")
    assert np.allclose(aef.dequantize(x), ((x / 127.5) ** 2) * np.sign(x))


def test_toa_do_ra_hang_cot_theo_luoi_kinh_vi_do():
    from app.services import aef
    assert aef.pixel(aef.Y0 - 0.5 * aef.GSD, -180 + 0.5 * aef.GSD) == (0, 0)
    r1, c1 = aef.pixel(12.68, 108.05)
    r2, c2 = aef.pixel(12.68 - aef.GSD, 108.05 + aef.GSD)
    assert (r2 - r1, c2 - c1) == (1, 1)                 # đi xuống nam = hàng tăng, sang đông = cột tăng
    with pytest.raises(ValueError):
        aef.window(12, 108, 12.001, 108.001, 2016)


def test_hoi_quy_logistic_tach_duoc_du_lieu_tach_roi_va_do_dung():
    from app.ml import aef_model
    rng = np.random.default_rng(0)
    X = np.vstack([rng.normal(1, 0.3, (200, 64)), rng.normal(-1, 0.3, (150, 64))])
    y = np.array([1] * 200 + [0] * 150)
    w, b = aef_model._fit(X, y, 1.0)
    p = 1 / (1 + np.exp(-(X @ w + b)))
    m = aef_model._metrics(p, y)
    assert m["balanced_accuracy"] == 1.0 and m["confusion"] == {"tp": 200, "tn": 150, "fp": 0, "fn": 0}


def test_giao_thuc_dang_ky_truoc_va_trang_thai_khi_chua_co_mo_hinh(monkeypatch, tmp_path):
    from app.ml import aef_model
    P = json.load(open(aef_model.PROTOCOL, encoding="utf-8"))
    assert P["registered"] == "2026-10-08" and P["h1_weak_labels"]["pass"] == {"balanced_accuracy_test": 0.85,
                                                                              "forest_recall_test": 0.90}
    assert "KHÔNG huấn luyện lại" in P["h2_human_labels"]["model"].upper() or "không huấn luyện lại" in P["h2_human_labels"]["model"]
    monkeypatch.setattr(aef_model, "MODEL", str(tmp_path / "none.json"))
    s = aef_model.status()
    assert s["available"] is False and "Google DeepMind" in s["attribution"] and s["message"]


def test_api_du_doan_tra_xac_suat_va_do_doi_thu_nghiem(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.ml import aef_model
    from app.services import aef, quota
    quota.reset()
    model = {"kind": "aef-logreg", "year": 2020, "w": [1.0] + [0.0] * 63, "b": 0.0,
             "run": {"date": "2026-10-08", "test": {"balanced_accuracy": 0.9, "forest_recall": 0.92}}}
    mp = tmp_path / "aef_model.json"
    mp.write_text(json.dumps(model), encoding="utf-8")
    monkeypatch.setattr(aef_model, "MODEL", str(mp))
    e = np.zeros(64, "float32"); e[0] = 1.0
    f = np.zeros(64, "float32"); f[1] = 1.0
    monkeypatch.setattr(aef, "mean_embedding", lambda la0, lo0, la1, lo1, year: ((e if year == 2020 else f), 9))
    geom = {"type": "Polygon", "coordinates": [[[108.05, 12.68], [108.051, 12.68], [108.051, 12.681],
                                                [108.05, 12.681], [108.05, 12.68]]]}
    with TestClient(app) as c:
        st = c.get("/api/eudr/ai/aef/status").json()
        assert st["available"] is True
        r = c.post("/api/eudr/ai/aef", json={"geometry": geom}).json()
    assert r["probability_forest"] == round(1 / (1 + np.exp(-1.0)), 3)
    assert r["change"]["status"] == "experimental" and r["change"]["cosine_2020_2025"] == 0.0
    assert "Google DeepMind" in r["attribution"]

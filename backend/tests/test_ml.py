"""Kiểm thử lớp học máy: đại số, huấn luyện, và các ràng buộc trung thực.

Nhóm test cuối cùng mới là nhóm quan trọng nhất. Chúng không kiểm tra mô hình
CHẠY ĐÚNG — chúng kiểm tra mô hình KHÔNG VƯỢT QUYỀN: không bịa số khi chưa
huấn luyện, không tự nâng mức rủi ro của module, và không giấu những mức mà nó
thua. Một mô hình sai thì sửa được; một mô hình lặng lẽ bịa thì phá cả sản phẩm.
"""
from __future__ import annotations

import json
import math
import os

import pytest

from app.ml import dataset, linalg, model
from app.services import anomaly_ml


# ───────────────────────────── đại số tuyến tính ─────────────────────────────

def _rand(seed: int):
    st = seed

    def n():
        nonlocal st
        st = (1103515245 * st + 12345) & 0x7FFFFFFF
        return st / 0x7FFFFFFF - 0.5
    return n


@pytest.mark.parametrize("d", [2, 5, 10])
def test_nghich_dao_nhan_lai_ra_ma_tran_don_vi(d):
    r = _rand(11 + d)
    a = [[r() for _ in range(d)] for _ in range(d)]
    for i in range(d):
        a[i][i] += d                      # chéo trội → chắc chắn khả nghịch
    inv = linalg.inverse(a)
    assert inv is not None
    for i in range(d):
        for j in range(d):
            got = sum(a[i][k] * inv[k][j] for k in range(d))
            assert abs(got - (1.0 if i == j else 0.0)) < 1e-9


def test_ma_tran_suy_bien_tra_none_chu_khong_tra_bua():
    """Suy biến phải trả None. Trả bừa một ma trận nào đó là kiểu hỏng tệ nhất:
    mô hình vẫn chạy, vẫn ra số, và số đó vô nghĩa."""
    assert linalg.inverse([[1.0, 2.0], [2.0, 4.0]]) is None
    assert linalg.inverse([[0.0, 0.0], [0.0, 0.0]]) is None


def test_mahalanobis_bang_tong_binh_phuong_khi_khong_tuong_quan():
    ident = [[1.0, 0.0], [0.0, 1.0]]
    assert linalg.mahalanobis_sq([3.0, 4.0], [0.0, 0.0], ident) == pytest.approx(25.0)


def test_mahalanobis_bat_duoc_to_hop_pha_vo_tuong_quan():
    """LÝ DO TỒN TẠI CỦA CẢ LỚP NÀY.

    Hai biến thường đi cùng nhau (tương quan 0,9). Cùng độ lớn, nhưng đi ngược
    chiều nhau phải bất thường hơn hẳn đi cùng chiều. Cách xét từng biến một
    cho hai trường hợp này ĐIỂM BẰNG NHAU — đó chính là lỗ hổng cần vá.
    """
    inv = linalg.inverse(linalg.ridge([[1.0, 0.9], [0.9, 1.0]], 0.0))
    cung = linalg.mahalanobis_sq([2.0, 2.0], [0.0, 0.0], inv)
    nguoc = linalg.mahalanobis_sq([2.0, -2.0], [0.0, 0.0], inv)
    assert nguoc > cung * 10


def test_ridge_khong_lam_hong_ma_tran_tot():
    cov = [[2.0, 0.3], [0.3, 1.5]]
    r = linalg.ridge(cov)
    for i in range(2):
        for j in range(2):
            assert abs(r[i][j] - cov[i][j]) < 0.01


def test_percentile_va_quantile_khop_nhau():
    s = [float(i) for i in range(1000)]
    for q in (10.0, 50.0, 90.0, 97.0):
        v = linalg.quantile(s, q)
        assert abs(linalg.percentile_of(s, v) - q) < 1.5


# ─────────────────────────────── đặc trưng ───────────────────────────────

def _chuoi(n: int, mua: float = 5.0):
    return [{"date": f"2020-{1 + i // 28:02d}-{1 + i % 28:02d}",
             "precip": mua, "et0": 3.0, "tmax": 30.0, "tmin": 22.0, "wind": 10.0}
            for i in range(n)]


def test_bo_qua_ngay_dau_vi_chua_du_nen_lich_su():
    rows = _chuoi(dataset.WARMUP + 10)
    f = dataset.build_features(rows)
    assert len(f) == 10, "phải bỏ đúng WARMUP ngày đầu"


def test_khong_noi_suy_ngay_thieu():
    """Ngày khuyết bị LOẠI, không bị bù bằng trung bình.

    Bù số sẽ tạo ra những ngày 'bình thường nhân tạo' và làm mô hình tưởng thế
    giới ổn định hơn thực tế — đúng loại sai lệch nguy hiểm nhất với cảnh báo.
    """
    rows = _chuoi(dataset.WARMUP + 5)
    rows[-3]["tmax"] = None
    f = dataset.build_features(rows)
    assert len(f) == 4
    assert all(r["tmax"] is not None for r in f)


def test_dry_streak_dem_dung():
    rows = _chuoi(dataset.WARMUP + 3, mua=0.0)
    f = dataset.build_features(rows)
    assert f[-1]["dry_streak"] == dataset.WARMUP + 1


def test_co_bien_nho_dai_de_thay_han():
    """Bản đầu chỉ nhớ 15 ngày và mù với hạn tích tụ hàng tháng."""
    assert "rain_60d" in dataset.FEATURES
    assert "wb_60d" in dataset.FEATURES
    assert dataset.WARMUP >= 60


def test_vector_dung_thu_tu_features():
    rows = _chuoi(dataset.WARMUP + 2)
    r = dataset.build_features(rows)[0]
    v = dataset.vector(r)
    assert len(v) == len(dataset.FEATURES)
    assert v == [r[k] for k in dataset.FEATURES]


def test_chia_theo_thoi_gian_khong_chong_lan():
    """Chia ngẫu nhiên sẽ rò rỉ: ngày 12/10 vào tập học, 13/10 vào tập kiểm tra."""
    rows = ([{"date": f"2019-01-{i:02d}", "precip": 1.0, "et0": 2.0,
              "tmax": 30.0, "tmin": 20.0, "wind": 5.0} for i in range(1, 29)] +
            [{"date": f"2021-01-{i:02d}", "precip": 1.0, "et0": 2.0,
              "tmax": 30.0, "tmin": 20.0, "wind": 5.0} for i in range(1, 29)])
    tr, te = dataset.split(dataset.build_features(rows))
    assert all(r["date"] <= dataset.TRAIN_END for r in tr)
    assert all(r["date"] >= dataset.TEST_START for r in te)
    assert not (set(r["date"] for r in tr) & set(r["date"] for r in te))


# ──────────────────────────── k-means & khớp vùng ────────────────────────────

def test_kmeans_tach_dung_hai_cum_tach_biet():
    pts = [[0.0, 0.0], [0.1, 0.1], [0.0, 0.2]] + [[9.0, 9.0], [9.1, 9.2], [8.9, 9.0]]
    _, lab = model.kmeans(pts, 2)
    assert lab[0] == lab[1] == lab[2]
    assert lab[3] == lab[4] == lab[5]
    assert lab[0] != lab[3]


def test_kmeans_tai_lap_duoc():
    """Hạt giống cố định → huấn luyện lại phải ra đúng kết quả cũ."""
    pts = [[float(i % 7), float(i % 5)] for i in range(40)]
    a = model.kmeans(pts, 3)
    b = model.kmeans(pts, 3)
    assert a[1] == b[1]


def test_fit_regime_tu_choi_khi_qua_it_du_lieu():
    assert model.fit_regime([[0.0] * 10 for _ in range(50)]) is None


# ───────────────────── mô hình đã huấn luyện (nếu có file) ─────────────────────

_M = model.load()
_co_model = pytest.mark.skipif(_M is None, reason="chưa chạy python -m app.ml.train")


@_co_model
def test_model_da_luu_du_thanh_phan():
    assert _M.blob["version"] == 1
    assert _M.features == dataset.FEATURES
    for r in _M.regimes:
        assert len(r["mu"]) == len(dataset.FEATURES)
        assert len(r["inv"]) == len(dataset.FEATURES)
        assert len(r["grid"]) == model.GRID_STEPS
        assert r["n"] >= 400


@_co_model
def test_phan_vi_tang_don_dieu_theo_d2():
    reg = _M.regimes[0]
    truoc = -1.0
    for d2 in (0.0, 1.0, 5.0, 20.0, 100.0, 1e6):
        p = model.percentile(reg, d2)
        assert 0.0 <= p <= 100.0
        assert p >= truoc
        truoc = p


@_co_model
def test_diem_binh_thuong_ra_phan_vi_thap():
    """Đúng trung tâm phân bố thì phải gần 0, không phải một số bất kỳ."""
    reg = _M.regimes[0]
    assert model.percentile(reg, linalg.mahalanobis_sq(
        reg["mu"], reg["mu"], reg["inv"])) < 5.0


@_co_model
def test_danh_gia_dung_su_kien_ngoai_tam_va_khong_giau_cho_thua():
    """Thẻ mô hình phải giữ MỌI mức đã thử, kể cả mức nó không thắng."""
    mt = _M.blob["metrics"]
    rates = [c["alarm_rate"] for c in mt["comparison"]]
    assert 1.0 in rates and 2.0 in rates
    hoa = [c for c in mt["comparison"]
           if c["joint_detected"] == c["baseline_detected"]]
    assert hoa, "báo cáo chỉ toàn thắng là dấu hiệu đã lọc bớt kết quả"


@_co_model
def test_chi_tinh_diem_tren_su_kien_trong_tam():
    """Bến Tre 2020 do thượng nguồn Mekong, không có dấu vết khí tượng tại chỗ."""
    ev = _M.blob["metrics"]["comparison"][0]["joint_events"]
    ngoai = [e for e in ev if not e["in_scope"]]
    assert len(ngoai) == 1 and ngoai[0]["site"] == "bentre"


@_co_model
def test_kiem_tra_tren_tinh_chua_tung_huan_luyen():
    loo = _M.blob["metrics"]["leave_one_out"]
    assert len(loo) >= 3
    assert sum(1 for e in loo if e["detected"]) >= 2, (
        "mô hình phải chạy được ở tỉnh chưa từng thấy, không chỉ 16 điểm đã học")


# ─────────────────── RÀNG BUỘC TRUNG THỰC — nhóm quan trọng nhất ───────────────────

def _ma_nguon(path: str) -> str:
    """Mã thật, đã bỏ chú thích và docstring — để test bắt CODE chứ không bắt văn."""
    import ast
    src = open(path, "r", encoding="utf-8").read()
    cay = ast.parse(src)
    for node in ast.walk(cay):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef, ast.Module)):
            d = ast.get_docstring(node)
            if d:
                src = src.replace(d, "")
    return "\n".join(d.split("#")[0] for d in src.split("\n")).lower()


def test_lop_du_lieu_tuyet_doi_khong_sinh_so():
    """dataset.py là nơi dữ liệu đi vào. Ở đây KHÔNG được có bất kỳ nguồn số giả nào.

    Cùng kỷ luật đã áp cho lớp vệ tinh: thiếu thì trả None, không bịa. Nếu lớp
    này bịa được thì mọi con số phía trên đều mất giá trị, kể cả khi mô hình đúng.
    """
    cam = ("random", "fake", "mock", "demo", "dummy", "synthetic", "gauss")
    code = _ma_nguon(dataset.__file__)
    for tu in cam:
        assert tu not in code, f"dataset.py chứa '{tu}' — lớp dữ liệu không được bịa"


def test_bo_sinh_so_cua_kmeans_phai_tu_chua_va_co_hat_giong():
    """model.py ĐƯỢC dùng số giả ngẫu nhiên, nhưng chỉ để khởi tạo k-means.

    Ranh giới rõ ràng: sinh số để CHỌN ĐIỂM BẮT ĐẦU của thuật toán gom cụm là
    chuyện bình thường; sinh số để LÀM DỮ LIỆU thì không. Ràng buộc ở đây là
    hạt giống cố định và không nhập thư viện random của Python — nhờ vậy huấn
    luyện lại luôn cho đúng kết quả cũ và không ai lén đưa nhiễu vào.
    """
    code = _ma_nguon(model.__file__)
    assert "import random" not in code
    assert "from random" not in code
    assert "_seed" in code, "phải có hạt giống cố định"
    for tu in ("fake", "mock", "dummy", "synthetic"):
        assert tu not in code, f"model.py chứa '{tu}'"


def test_lop_chay_that_khong_co_nhanh_gia_lap():
    code = _ma_nguon(anomaly_ml.__file__)
    for tu in ("random", "fake", "mock", "dummy", "synthetic"):
        assert tu not in code, f"anomaly_ml.py chứa '{tu}'"


def test_score_tra_none_khi_chua_huan_luyen(monkeypatch):
    monkeypatch.setattr(anomaly_ml, "_MODEL", None)
    monkeypatch.setattr(anomaly_ml, "_LOADED", True)
    assert anomaly_ml.score(16.46, 107.59) is None
    assert anomaly_ml.model_card()["available"] is False


def test_the_mo_hinh_noi_ro_vai_tro_doi_chieu():
    """Mô hình KHÔNG được quyền thay baseline — vì nó chỉ hoà ở mức vận hành."""
    card = anomaly_ml.model_card()
    if not card.get("available"):
        pytest.skip("chưa huấn luyện")
    assert "đối chiếu" in card["role"].lower()
    assert "không thay thế" in card["role"].lower()


@_co_model
def test_ket_qua_score_luon_kem_canh_bao_gioi_han(monkeypatch):
    """Mọi kết quả trả ra phải nói rõ nó đo ĐỘ HIẾM chứ không đo MỨC NGUY HIỂM."""
    m = _M
    monkeypatch.setattr(anomaly_ml, "_MODEL", m)
    monkeypatch.setattr(anomaly_ml, "_LOADED", True)
    monkeypatch.setattr(anomaly_ml, "_local",
                        lambda lat, lon: ([0.0] * len(dataset.FEATURES),
                                          [1.0] * len(dataset.FEATURES), 0))
    rows = _chuoi(dataset.WARMUP + 2)
    monkeypatch.setattr(anomaly_ml, "_archive", lambda *a, **k: rows)
    r = anomaly_ml.score(16.0, 107.0)
    assert r is not None
    assert "hiếm" in r["caveat"].lower()
    assert "không thay đổi mức rủi ro" in r["role"].lower()


@_co_model
def test_model_khong_phinh_qua_muc():
    """Artefact phải đủ nhỏ để đi kèm mã nguồn, không cần kho lưu trữ riêng."""
    assert os.path.getsize(model.MODEL_PATH) < 400 * 1024

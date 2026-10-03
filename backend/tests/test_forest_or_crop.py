"""Mô hình "Rừng hay vườn cây?": đặc trưng 12 tháng, suy luận numpy khớp PyTorch, vòng
huấn luyện → chấm một lần → chỉ xuất mô hình khi qua ngưỡng. Không chạm mạng."""
from __future__ import annotations

import json

import numpy as np
import pytest

from app.ml import forest_or_crop as foc


def test_dac_trung_khoi_va_noi_suy_thang_trong():
    rng = np.random.default_rng(0)
    comp = rng.uniform(0.02, 0.4, (12, 6, 40, 40)).astype(np.float32)
    comp[:, 3] += 0.3                                  # B08 cao → NDVI dương
    comp[2, :, :10, :10] = np.nan                      # tháng 3 mây ở một ô
    F, ok = foc.block_features(comp, block=10)
    assert F.shape == (16, len(foc.FEATURE_NAMES)) and ok.all()
    assert np.isfinite(F).all()
    comp[:, :, :10, :10] = np.nan                      # ô mây cả năm → loại
    F, ok = foc.block_features(comp, block=10)
    assert not ok[0] and ok[1:].all()


def test_tach_theo_vi_do():
    assert foc.split_of(13.0) == "train" and foc.split_of(14.5) == "val" and foc.split_of(11.5) == "test"
    assert foc.split_of(15.0) == "val" and foc.split_of(10.0) == "none"


def _torch():
    return pytest.importorskip("torch")


def test_suy_luan_numpy_khop_torch_ca_ba_kien_truc():
    torch = _torch()
    from torch import nn
    rng = np.random.default_rng(1)
    X = rng.normal(size=(50, len(foc.FEATURE_NAMES))).astype(np.float32)
    mean, std = np.zeros(X.shape[1]), np.ones(X.shape[1])
    torch.manual_seed(0)
    mlp = nn.Sequential(nn.Linear(X.shape[1], 8), nn.ReLU(), nn.Linear(8, 4), nn.ReLU(), nn.Linear(4, 1))
    sd = {k: v.detach().numpy().tolist() for k, v in mlp.state_dict().items()}
    m = {"kind": "mlp", "layers": [[sd["0.weight"], sd["0.bias"]], [sd["2.weight"], sd["2.bias"]], [sd["4.weight"], sd["4.bias"]]],
         "mean": mean, "std": std}
    with torch.no_grad():
        want = torch.sigmoid(mlp(torch.tensor(X))).numpy()[:, 0]
    assert np.max(np.abs(foc._np_forward(m, X) - want)) < 1e-5

    c1 = nn.Conv1d(2, 5, 3, padding=1, padding_mode="circular")
    c2 = nn.Conv1d(5, 5, 3, padding=1, padding_mode="circular")
    h1, h2 = nn.Linear(5 + X.shape[1] - 24, 6), nn.Linear(6, 1)
    with torch.no_grad():
        z = torch.tensor(X)
        s = torch.stack([z[:, :12], z[:, 12:24]], 1)
        h = torch.relu(c2(torch.relu(c1(s)))).mean(2)
        want = torch.sigmoid(h2(torch.relu(h1(torch.cat([h, z[:, 24:]], 1))))).numpy()[:, 0]
    t = lambda mod: [mod.weight.detach().numpy().tolist(), mod.bias.detach().numpy().tolist()]
    m = {"kind": "cnn1d", "convs": [t(c1), t(c2)], "head": [t(h1), t(h2)], "mean": mean, "std": std}
    assert np.max(np.abs(foc._np_forward(m, X) - want)) < 1e-5


def test_chi_so_can_bang():
    m = foc._metrics(np.array([0.9, 0.8, 0.2, 0.6]), np.array([1, 1, 0, 0]))
    assert m["forest_recall"] == 1.0 and m["tree_crop_recall"] == 0.5 and m["balanced_accuracy"] == 0.75


def test_huan_luyen_cham_mot_lan_va_chi_xuat_khi_dat(tmp_path, monkeypatch):
    _torch()
    rng = np.random.default_rng(2)
    n = 600
    y = rng.integers(0, 2, n)
    lat = np.concatenate([rng.uniform(12.0, 14.2, 400), rng.uniform(14.2, 15.0, 100), rng.uniform(11.3, 12.0, 100)])
    months = np.arange(12)
    # rừng: NDVI cao, phẳng; vườn cây: NDVI thấp hơn, tụt mùa khô (tháng 1–4)
    nd = np.where(y[:, None] == 1, 0.82, 0.62 - 0.15 * np.isin(months, [0, 1, 2, 3])[None, :]) + rng.normal(0, 0.03, (n, 12))
    nm = nd - 0.3 + rng.normal(0, 0.03, (n, 12))
    rest = rng.normal(0.2, 0.05, (n, 10))
    X = np.concatenate([nd, nm, rest], axis=1).astype(np.float32)
    np.savez_compressed(tmp_path / "ds.npz", X=X, y=y.astype(np.int8), lat=lat, lon=np.zeros(n), maps=np.zeros((n, 3)))
    monkeypatch.setattr(foc, "DATASET", str(tmp_path / "ds.npz"))
    monkeypatch.setattr(foc, "RUNS", str(tmp_path / "runs.json"))
    monkeypatch.setattr(foc, "MODEL", str(tmp_path / "model.json"))
    foc.train()
    run = json.load(open(tmp_path / "runs.json", encoding="utf-8"))[-1]
    assert run["passed"] and run["numpy_vs_torch_max_diff"] < 1e-4 and run["n"] == {"train": 400, "val": 100, "test": 100}
    model = json.load(open(tmp_path / "model.json", encoding="utf-8"))
    assert model["kind"] in ("logreg", "mlp", "cnn1d") and model["run"]["status"] == "accepted"

    # Dữ liệu nhiễu thuần (không học được) → KHÔNG xuất mô hình, vẫn ghi lần trượt.
    (tmp_path / "model.json").unlink()
    np.savez_compressed(tmp_path / "ds.npz", X=rng.normal(size=(n, 34)).astype(np.float32), y=y.astype(np.int8),
                        lat=lat, lon=np.zeros(n), maps=np.zeros((n, 3)))
    foc.train()
    runs = json.load(open(tmp_path / "runs.json", encoding="utf-8"))
    assert len(runs) == 2 and runs[-1]["status"] == "rejected" and not (tmp_path / "model.json").exists()

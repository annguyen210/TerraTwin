"""Huấn luyện U-Net phân đoạn lớp phủ. Chạy trên máy có GPU của bạn.

    python -m app.dl.train --smoke     ← chạy cái này TRƯỚC, mất 30 giây
    python -m app.dl.train

VÌ SAO U-NET VÀ KHÔNG PHẢI CÁI GÌ TO HƠN. Bài toán là phân đoạn ảnh 4 kênh
256×256 với 11 lớp, dữ liệu cỡ vài trăm tới vài nghìn ô. U-Net là kiến trúc
đúng tầm: đủ sâu để học kết cấu và hình dạng — thứ mà chỉ số phổ không thấy —
nhưng không lớn tới mức học thuộc lòng một bộ dữ liệu nhỏ. Dùng một mô hình
khổng lồ ở đây sẽ cho điểm huấn luyện đẹp và điểm thực tế tệ.

CHIA TẬP THEO ĐỊA ĐIỂM, KHÔNG THEO Ô. Hai ô cách nhau 2 km ở cùng một huyện gần
như giống hệt nhau. Chia ngẫu nhiên theo ô thì mạng đã thấy vùng đó lúc học và
điểm kiểm tra đẹp một cách giả tạo — đúng loại rò rỉ đã suýt xảy ra ở lớp mô
hình khí hậu. Ở đây giữ NGUYÊN CỤM: một số tỉnh bị giữ lại hoàn toàn khỏi tập
huấn luyện.

CHẤM BẰNG IoU TỪNG LỚP, KHÔNG CHẤM BẰNG ĐỘ CHÍNH XÁC TỔNG. Ở Việt Nam lớp "tán
cây" chiếm phần lớn diện tích, nên một mạng đoán "tán cây" cho mọi điểm ảnh vẫn
đạt độ chính xác rất cao mà hoàn toàn vô dụng. Chính là cái bẫy POD-100% đã làm
hỏng bản backtest đầu tiên của dự án này. Lớp đáng quan tâm nhất là "bề mặt xây
dựng" — nó hiếm, và nó là thứ mô-đun xây dựng trái phép cần.

TỆP NÀY CHƯA CHẠY THỬ ĐƯỢC trên máy viết ra nó (không có GPU, không cài được
torch). Chế độ --smoke chạy đủ một vòng trên dữ liệu hình dạng thật để bắt lỗi
kích thước và lỗi cú pháp trong nửa phút.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time


def build_unet(in_ch: int, n_classes: int, base: int = 32):
    import torch
    import torch.nn as nn

    def block(a, b):
        return nn.Sequential(
            nn.Conv2d(a, b, 3, padding=1, bias=False), nn.BatchNorm2d(b), nn.ReLU(True),
            nn.Conv2d(b, b, 3, padding=1, bias=False), nn.BatchNorm2d(b), nn.ReLU(True))

    class UNet(nn.Module):
        def __init__(self):
            super().__init__()
            c = base
            self.e1, self.e2, self.e3, self.e4 = (
                block(in_ch, c), block(c, c * 2), block(c * 2, c * 4), block(c * 4, c * 8))
            self.pool = nn.MaxPool2d(2)
            self.u3 = nn.ConvTranspose2d(c * 8, c * 4, 2, 2)
            self.d3 = block(c * 8, c * 4)
            self.u2 = nn.ConvTranspose2d(c * 4, c * 2, 2, 2)
            self.d2 = block(c * 4, c * 2)
            self.u1 = nn.ConvTranspose2d(c * 2, c, 2, 2)
            self.d1 = block(c * 2, c)
            self.out = nn.Conv2d(c, n_classes, 1)

        def forward(self, x):
            e1 = self.e1(x)
            e2 = self.e2(self.pool(e1))
            e3 = self.e3(self.pool(e2))
            e4 = self.e4(self.pool(e3))
            d3 = self.d3(torch.cat([self.u3(e4), e3], 1))
            d2 = self.d2(torch.cat([self.u2(d3), e2], 1))
            d1 = self.d1(torch.cat([self.u1(d2), e1], 1))
            return self.out(d1)

    return UNet()


def iou_per_class(conf):
    """IoU từng lớp từ ma trận nhầm lẫn. None cho lớp không xuất hiện."""
    out = []
    for i in range(conf.shape[0]):
        tp = conf[i, i]
        fp = conf[:, i].sum() - tp
        fn = conf[i, :].sum() - tp
        den = tp + fp + fn
        out.append(float(tp / den) if den > 0 else None)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/dl/patches.npz")
    ap.add_argument("--out", default="data/dl")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--base", type=int, default=32)
    ap.add_argument("--holdout", default="Cần Thơ,Đà Nẵng,Hà Giang,Cần Giờ",
                    help="tỉnh giữ lại HOÀN TOÀN khỏi tập huấn luyện")
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()

    try:
        import numpy as np
        import torch
        import torch.nn as nn
    except ImportError:
        print("Thiếu thư viện. Cài trước:")
        print("    pip install torch --index-url https://download.pytorch.org/whl/cu121")
        print("    pip install numpy")
        return 1

    from app.dl.fetch import N_CLASSES, WC_NAMES

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Thiết bị: {dev}"
          + (f" · {torch.cuda.get_device_name(0)}" if dev == "cuda" else " (KHÔNG có GPU — sẽ rất chậm)"))

    if a.smoke:
        print("\nChạy thử một vòng trên dữ liệu giả ĐÚNG HÌNH DẠNG thật…")
        net = build_unet(4, N_CLASSES, a.base).to(dev)
        n_par = sum(p.numel() for p in net.parameters())
        x = torch.rand(2, 4, 256, 256, device=dev)
        y = torch.randint(0, N_CLASSES, (2, 256, 256), device=dev)
        opt = torch.optim.AdamW(net.parameters(), lr=a.lr)
        lossf = nn.CrossEntropyLoss(ignore_index=255)
        t = time.time()
        out = net(x)
        loss = lossf(out, y)
        loss.backward()
        opt.step()
        print(f"  tham số     {n_par:,}")
        print(f"  vào  {tuple(x.shape)} → ra {tuple(out.shape)}")
        print(f"  mất mát     {loss.item():.4f}")
        print(f"  một vòng    {time.time() - t:.2f}s")
        assert out.shape == (2, N_CLASSES, 256, 256), "kích thước đầu ra sai"
        print("\nOK. Chạy thật: python -m app.dl.train")
        return 0

    if not os.path.exists(a.data):
        print(f"Chưa có {a.data}. Chạy trước: python -m app.dl.fetch")
        return 1

    d = np.load(a.data)
    X, Y = d["X"], d["Y"]
    with open(os.path.join(os.path.dirname(a.data), "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)["meta"]

    # CHIA THEO TỈNH — xem lý do ở đầu tệp.
    hold = {s.strip() for s in a.holdout.split(",") if s.strip()}
    te_idx = [i for i, m in enumerate(meta)
              if any(h in m["site"] for h in hold)]
    tr_idx = [i for i in range(len(meta)) if i not in set(te_idx)]
    if not te_idx or not tr_idx:
        print("Chia tập hỏng — kiểm tra --holdout khớp tên trong meta.json")
        return 1
    print(f"\nHuấn luyện {len(tr_idx)} ô · kiểm tra {len(te_idx)} ô "
          f"(giữ lại hoàn toàn: {', '.join(sorted(hold))})")

    Xtr = torch.from_numpy(X[tr_idx]); Ytr = torch.from_numpy(Y[tr_idx]).long()
    Xte = torch.from_numpy(X[te_idx]); Yte = torch.from_numpy(Y[te_idx]).long()

    # Cân bằng lớp: lớp hiếm (bề mặt xây dựng) phải được đếm nặng hơn, nếu không
    # mạng sẽ bỏ qua nó để tối ưu con số tổng.
    cnt = torch.bincount(Ytr[Ytr != 255].flatten(), minlength=N_CLASSES).float()
    w = torch.where(cnt > 0, cnt.sum() / (N_CLASSES * cnt.clamp(min=1)),
                    torch.zeros_like(cnt))
    print("  trọng số lớp:", " ".join(f"{WC_NAMES[i][:8]}={w[i]:.2f}"
                                      for i in range(N_CLASSES) if cnt[i] > 0))

    net = build_unet(X.shape[1], N_CLASSES, a.base).to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=a.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=a.epochs)
    lossf = nn.CrossEntropyLoss(weight=w.to(dev), ignore_index=255)

    best = -1.0
    t0 = time.time()
    for ep in range(1, a.epochs + 1):
        net.train()
        perm = torch.randperm(len(Xtr))
        tot = 0.0
        for i in range(0, len(perm), a.batch):
            b = perm[i:i + a.batch]
            xb, yb = Xtr[b].to(dev), Ytr[b].to(dev)
            # Xoay/lật ngẫu nhiên — lớp phủ không có hướng ưu tiên, nên đây là
            # phép tăng dữ liệu hợp lý về mặt vật lý.
            if torch.rand(1).item() < 0.5:
                xb, yb = torch.flip(xb, [3]), torch.flip(yb, [2])
            if torch.rand(1).item() < 0.5:
                xb, yb = torch.flip(xb, [2]), torch.flip(yb, [1])
            opt.zero_grad()
            loss = lossf(net(xb), yb)
            loss.backward()
            opt.step()
            tot += loss.item() * len(b)
        sched.step()

        net.eval()
        conf = torch.zeros(N_CLASSES, N_CLASSES, dtype=torch.long)
        with torch.no_grad():
            for i in range(0, len(Xte), a.batch):
                xb = Xte[i:i + a.batch].to(dev)
                yb = Yte[i:i + a.batch]
                pr = net(xb).argmax(1).cpu()
                m = yb != 255
                idx = yb[m] * N_CLASSES + pr[m]
                conf += torch.bincount(
                    idx.flatten(), minlength=N_CLASSES ** 2).reshape(N_CLASSES, N_CLASSES)
        ious = iou_per_class(conf.numpy())
        valid = [v for v in ious if v is not None]
        miou = sum(valid) / len(valid) if valid else 0.0
        xd = ious[WC_NAMES.index("Bề mặt xây dựng")]

        if ep % 5 == 0 or ep == 1 or ep == a.epochs:
            print(f"  vòng {ep:3}  mất mát {tot / len(Xtr):.4f}  "
                  f"mIoU {miou:.3f}  IoU xây dựng {xd if xd is None else round(xd, 3)}"
                  f"  ({time.time() - t0:.0f}s)")
        if miou > best:
            best = miou
            os.makedirs(a.out, exist_ok=True)
            torch.save({"state": net.state_dict(), "in_ch": X.shape[1],
                        "base": a.base, "n_classes": N_CLASSES,
                        "miou": miou, "iou": ious, "epoch": ep,
                        "holdout": sorted(hold)},
                       os.path.join(a.out, "unet_landcover.pt"))

    print(f"\nmIoU tốt nhất trên tỉnh chưa từng thấy: {best:.3f}")
    print("IoU từng lớp:")
    ck = torch.load(os.path.join(a.out, "unet_landcover.pt"), map_location="cpu")
    for i, v in enumerate(ck["iou"]):
        print(f"  {WC_NAMES[i]:22} {'—' if v is None else f'{v:.3f}'}")

    # NGƯỠNG CHẤP NHẬN, đặt TRƯỚC khi biết kết quả: dưới mức này thì mô hình
    # không được đưa vào sản phẩm, kể cả khi nó là thứ mới nhất.
    print()
    if best < 0.35:
        print("KHÔNG ĐẠT (mIoU < 0,35). Đừng bật vào sản phẩm — cần thêm dữ liệu.")
    else:
        print("ĐẠT. Bước tiếp: python -m app.dl.export")
    return 0


if __name__ == "__main__":
    sys.exit(main())

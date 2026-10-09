"""Trình GIẢ LẬP thiết bị IoT ký số cho TerraTwin — để demo và để người làm phần cứng đối chiếu.

Thiết bị thật (ESP32 + cảm biến ẩm đất/nhiệt/mưa) làm ĐÚNG các bước này:
  1. Sinh khoá Ed25519 MỘT lần, giữ khoá bí mật trong bộ nhớ an toàn của chip.
  2. Đăng ký khoá CÔNG KHAI với TerraTwin (trang /thiet-bi hoặc POST /api/iot/devices).
  3. Mỗi lần đo: payload = JSON {device_id, seq (tăng dần, lưu qua mất điện), ts, metrics};
     ký Ed25519 trên đúng chuỗi UTF-8 đó; gửi {payload, sig} — mất sóng thì lưu đệm, gửi bù
     tối đa 200 bản ghi mỗi lượt (POST /api/iot/ingest).
  Trên ESP32: libsodium có sẵn trong ESP-IDF (crypto_sign_detached) làm được bước 3.

Số đo do trình này sinh là GIẢ LẬP (nhịp ngày đêm + nhiễu) và thiết bị được đăng ký với
kind="simulator" — TerraTwin luôn gắn nhãn "giả lập", không bao giờ lẫn với số đo thật.

    python ops/iot_simulator.py --api http://127.0.0.1:8000 --email a@b.vn --password ... \
        --name "Trạm thử" --count 48 --step-min 30
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import os
import random
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _post(url: str, body: dict, token: str | None = None) -> dict:
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=h)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def load_or_create_key(path: str) -> Ed25519PrivateKey:
    if os.path.exists(path):
        return Ed25519PrivateKey.from_private_bytes(base64.b64decode(open(path).read().strip()))
    k = Ed25519PrivateKey.generate()
    seed = k.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                           serialization.NoEncryption())
    with open(path, "w") as f:
        f.write(base64.b64encode(seed).decode())
    return k


def public_b64(k: Ed25519PrivateKey) -> str:
    return base64.b64encode(k.public_key().public_bytes(serialization.Encoding.Raw,
                                                        serialization.PublicFormat.Raw)).decode()


def synth(t: datetime, rng: random.Random, soil: float) -> tuple[dict, float]:
    """Nhịp ngày đêm giờ VN + đất khô dần, mưa rào ngẫu nhiên làm ẩm lại. GIẢ LẬP."""
    h = (t.hour + 7) % 24 + t.minute / 60
    air = 24 + 6 * math.sin((h - 9) / 24 * 2 * math.pi) + rng.gauss(0, 0.6)
    rain = round(rng.expovariate(1 / 6), 1) if rng.random() < 0.06 else 0.0
    soil = max(5.0, min(60.0, soil - 0.25 + rain * 1.5 + rng.gauss(0, 0.2)))
    return {"soil_moisture_pct": round(soil, 1), "air_temp_c": round(air, 1),
            "humidity_pct": round(max(30, min(100, 95 - (air - 22) * 4 + rng.gauss(0, 2))), 1),
            "rain_mm": rain, "battery_v": round(3.9 - rng.random() * 0.1, 2)}, soil


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--name", default="Trạm giả lập")
    ap.add_argument("--key", default="iot_sim_key.txt", help="tệp khoá bí mật (giữ kín, KHÔNG commit)")
    ap.add_argument("--device-id", help="đã đăng ký rồi thì truyền id để gửi tiếp")
    ap.add_argument("--count", type=int, default=48)
    ap.add_argument("--step-min", type=int, default=30)
    ap.add_argument("--seq-start", type=int, default=1)
    # GĐ6 — trình diễn "nhúng đầu đo vào cốc nước muối": gửi thêm độ mặn (‰) và EC (mS/cm ≈ ‰ / 0,68).
    ap.add_argument("--salinity", type=float, help="độ mặn ‰ cho các số đo (vd 0.5 nước ngọt, 35 nước biển)")
    ap.add_argument("--lat", type=float, help="vị trí thiết bị — nhật ký thửa gắn thiết bị trong 500 m")
    ap.add_argument("--lon", type=float)
    a = ap.parse_args()

    tok = _post(f"{a.api}/api/auth/login", {"email": a.email, "password": a.password})["access_token"]
    k = load_or_create_key(a.key)
    dev_id = a.device_id
    if not dev_id:
        body = {"name": a.name, "public_key": public_b64(k), "kind": "simulator"}
        if a.lat is not None and a.lon is not None:
            body.update(lat=a.lat, lon=a.lon)
        dev = _post(f"{a.api}/api/iot/devices", body, token=tok)
        dev_id = dev["id"]
        print("đã đăng ký thiết bị giả lập", dev_id)
    rng = random.Random(dev_id)
    now = datetime.now(timezone.utc)
    soil, batch = 32.0, []
    for i in range(a.count):                       # gửi BÙ: các mốc trong quá khứ tới hiện tại
        t = now - timedelta(minutes=a.step_min * (a.count - 1 - i))
        m, soil = synth(t, rng, soil)
        if a.salinity is not None:
            m.update(salinity_ppt=round(a.salinity, 2), ec_ms_cm=round(a.salinity / 0.68, 2))
        payload = json.dumps({"device_id": dev_id, "seq": a.seq_start + i,
                              "ts": t.isoformat(timespec="seconds"), "metrics": m}, ensure_ascii=False)
        batch.append({"payload": payload, "sig": base64.b64encode(k.sign(payload.encode())).decode()})
    out = _post(f"{a.api}/api/iot/ingest", {"device_id": dev_id, "readings": batch})
    print("nhận", out["accepted"], "· từ chối", len(out["rejected"]), "· seq cuối", out["last_seq"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

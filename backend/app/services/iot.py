"""IOT KÝ SỐ — số đo tại vườn mà CHÍNH MÁY CHỦ cũng không giả được.

VÌ SAO KÝ TỪNG SỐ ĐO: một bảng "độ ẩm đất" trong cơ sở dữ liệu thì ai quản trị máy chủ
cũng sửa được — với người mua EU hay ngân hàng, đó chỉ là lời khai. Ở đây mỗi thiết bị
tự sinh khoá Ed25519 (khoá bí mật không rời thiết bị), ký từng số đo; máy chủ chỉ lưu
khoá công khai, chuỗi đã ký và chữ ký. Bất kỳ ai tải bản xuất về đều kiểm lại được.

KIỂM TRA KHI NHẬN (theo thứ tự, dừng ở lỗi đầu tiên):
  1. Thiết bị tồn tại, chưa bị thu hồi.
  2. Chữ ký Ed25519 đúng trên ĐÚNG chuỗi thiết bị gửi (không dựng lại chuỗi phía máy chủ:
     ESP32 ghi 23.50, Python ghi 23.5 — dựng lại là chữ ký "sai" dù số đo thật).
  3. device_id trong chuỗi khớp thiết bị gửi (chống lấy gói của thiết bị khác).
  4. seq tăng nghiêm ngặt (chống phát lại gói cũ).
  5. Thời điểm đo: không ở tương lai (> 10 phút), không quá 30 ngày (cho phép gửi bù
     sau nhiều ngày mất sóng ở vườn).
  6. Chỉ số trong danh sách cho phép VÀ trong ngưỡng vật lý — "độ ẩm 140%" là cảm biến
     hỏng, nhận vào là làm bẩn dữ liệu của chính người dùng.
"""
from __future__ import annotations

import base64
import json
import secrets
from datetime import datetime, timedelta, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# chỉ số → (min, max, đơn vị, nhãn VI, nhãn EN)
METRICS = {
    "soil_moisture_pct": (0.0, 100.0, "%", "Độ ẩm đất", "Soil moisture"),
    "soil_temp_c": (-10.0, 70.0, "°C", "Nhiệt độ đất", "Soil temperature"),
    "air_temp_c": (-20.0, 60.0, "°C", "Nhiệt độ không khí", "Air temperature"),
    "humidity_pct": (0.0, 100.0, "%", "Độ ẩm không khí", "Air humidity"),
    "rain_mm": (0.0, 300.0, "mm", "Lượng mưa (kỳ đo)", "Rainfall (interval)"),
    "leaf_wetness_pct": (0.0, 100.0, "%", "Độ ướt lá", "Leaf wetness"),
    "battery_v": (0.0, 15.0, "V", "Điện áp pin", "Battery voltage"),
}
MAX_FUTURE = timedelta(minutes=10)
MAX_PAST = timedelta(days=30)
MAX_BATCH = 200
DRY_SOIL_PCT = 20.0          # dưới mức này: nhắc kiểm tra tưới (tham khảo, không phải khuyến cáo nông học)
SILENT_HOURS = 24


class Rejected(ValueError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


def new_id() -> str:
    return secrets.token_hex(6)


def parse_public_key(b64: str) -> str:
    """Kiểm và chuẩn hoá khoá công khai Ed25519 (base64 của đúng 32 byte)."""
    try:
        raw = base64.b64decode(b64.strip(), validate=True)
    except Exception as e:
        raise Rejected("bad_key", "khoá công khai không phải base64") from e
    if len(raw) != 32:
        raise Rejected("bad_key", "khoá Ed25519 phải đúng 32 byte")
    Ed25519PublicKey.from_public_bytes(raw)
    return base64.b64encode(raw).decode()


def verify_signature(public_b64: str, payload: str, sig_b64: str) -> bool:
    try:
        pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_b64))
        pub.verify(base64.b64decode(sig_b64, validate=True), payload.encode("utf-8"))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def _parse_time(v) -> datetime:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return datetime.fromtimestamp(float(v), tz=timezone.utc).replace(tzinfo=None)
    if isinstance(v, str):
        try:
            t = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError as e:
            raise Rejected("bad_time", "ts không phải ISO 8601 hay epoch") from e
        return (t.astimezone(timezone.utc).replace(tzinfo=None) if t.tzinfo else t)
    raise Rejected("bad_time", "thiếu ts")


def check(device, payload: str, sig: str, now: datetime | None = None) -> dict:
    """Kiểm MỘT số đo. Trả {seq, measured_at, metrics} hoặc ném Rejected."""
    if device is None or device.revoked:
        raise Rejected("unknown_device")
    if not verify_signature(device.public_b64, payload, sig):
        raise Rejected("bad_signature")
    try:
        d = json.loads(payload)
    except ValueError as e:
        raise Rejected("bad_payload", "không phải JSON") from e
    if not isinstance(d, dict) or d.get("device_id") != device.id:
        raise Rejected("device_mismatch")
    seq = d.get("seq")
    if not isinstance(seq, int) or isinstance(seq, bool) or seq <= device.last_seq:
        raise Rejected("replay", f"seq phải > {device.last_seq}")
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    t = _parse_time(d.get("ts"))
    if t > now + MAX_FUTURE:
        raise Rejected("bad_time", "thời điểm đo ở tương lai")
    if t < now - MAX_PAST:
        raise Rejected("bad_time", "số đo cũ hơn 30 ngày")
    m = d.get("metrics")
    if not isinstance(m, dict) or not m:
        raise Rejected("bad_metrics", "thiếu metrics")
    clean = {}
    for k, v in m.items():
        if k not in METRICS:
            raise Rejected("bad_metrics", f"chỉ số không hỗ trợ: {k}")
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v != v:
            raise Rejected("bad_metrics", f"{k} không phải số")
        lo, hi = METRICS[k][0], METRICS[k][1]
        if not (lo <= float(v) <= hi):
            raise Rejected("implausible", f"{k}={v} ngoài ngưỡng vật lý [{lo}, {hi}]")
        clean[k] = float(v)
    return {"seq": seq, "measured_at": t, "metrics": clean}


def status_items(devices: list, latest: dict, now: datetime | None = None, tr=None) -> list[dict]:
    """TỰ ĐỘNG HOÁ cho trang Hôm nay: thiết bị im lặng quá lâu, đất khô dưới ngưỡng.
    `latest` = {device_id: (measured_at, metrics)}. Ngưỡng là nhắc kiểm tra, không phải
    khuyến cáo nông học — nói rõ trong nội dung."""
    tr = tr or (lambda vi, en: vi)
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    out = []
    for dv in devices:
        if dv.revoked:
            continue
        sim = tr(" (giả lập)", " (simulated)") if dv.kind == "simulator" else ""
        if dv.last_seen is None or now - dv.last_seen > timedelta(hours=SILENT_HOURS):
            out.append({"kind": "device", "priority": "action", "link": "/thiet-bi",
                        "title": tr(f"Thiết bị “{dv.name}”{sim} im lặng hơn {SILENT_HOURS} giờ",
                                    f"Device “{dv.name}”{sim} silent for over {SILENT_HOURS} h"),
                        "body": tr("Kiểm tra pin, sóng điện thoại hoặc cảm biến tại vườn.",
                                   "Check battery, mobile signal or the sensor in the field.")})
            continue
        lt = latest.get(dv.id)
        if lt and lt[1].get("soil_moisture_pct") is not None and lt[1]["soil_moisture_pct"] < DRY_SOIL_PCT:
            out.append({"kind": "device", "priority": "action", "link": "/thiet-bi",
                        "title": tr(f"Đất khô tại “{dv.name}”{sim}: {lt[1]['soil_moisture_pct']:.0f}%",
                                    f"Dry soil at “{dv.name}”{sim}: {lt[1]['soil_moisture_pct']:.0f}%"),
                        "body": tr(f"Dưới {DRY_SOIL_PCT:.0f}% — nên kiểm tra tưới. Ngưỡng nhắc chung, không phải khuyến cáo theo giống cây.",
                                   f"Below {DRY_SOIL_PCT:.0f}% — consider checking irrigation. Generic reminder, not crop-specific advice.")})
    return out

"""MỘT CHẠM — hỏi đúng một câu, ngay trong tin nhắn cảnh báo, KHÔNG đăng nhập.

BÀI TOÁN ĐO ĐƯỢC
================
Kho quan sát thực địa — tài sản duy nhất của TerraTwin không tải được từ vệ
tinh — có 6 bản ghi, và cả 6 đều do test sinh ra. Giao diện gửi quan sát thì
vẫn tồn tại: nó nằm dưới màn cuộn, và mở ra là dòng "Đăng nhập để báo lại…".

Bắt một người nông dân lập tài khoản trước khi họ được phép nói cho ta biết
ruộng đã ngập là điểm chết của cả vòng lặp. Và kể cả có tài khoản, chẳng ai tự
nhớ ra mà vào báo. Phần mềm chưa bao giờ HỎI.

CÁCH LÀM
========
Khi cửa sổ cảnh báo khép lại, chính tin nhắn Zalo/Telegram mang theo một liên
kết ký số. Bấm vào là thấy đúng MỘT câu hỏi và ba nút:

    "Ngày 12/10 chúng tôi báo ngập thửa Ruộng Ba Tri. Có ngập thật không?"
                    [ Có ]   [ Không ]   [ Không rõ ]

ĐÚNG MỘT CÂU HỎI, KHÔNG BAO GIỜ HAI. Mỗi câu hỏi thêm vào cắt tỉ lệ trả lời đi
khoảng một nửa, và câu thứ nhất là câu duy nhất đáng giá: nó vừa chấm điểm cho
cảnh báo, vừa sinh ra một điểm ground-truth để hiệu chỉnh ngưỡng cho vùng đó.

VÌ SAO KHÔNG CẦN ĐĂNG NHẬP MÀ VẪN AN TOÀN
=========================================
Liên kết là một JWT ký bằng đúng khoá của phần mềm, chứa duy nhất id cảnh báo,
hết hạn sau 45 ngày. Nó KHÔNG phải phiên đăng nhập: cầm được nó chỉ trả lời
được đúng một câu hỏi về đúng một cảnh báo, không đọc được thửa, không xem
được cảnh báo khác, không đổi được gì trong tài khoản. Trả lời rồi thì lần bấm
sau chỉ hiện lại kết quả — không sửa được, để một liên kết bị chuyển tiếp
không thể lật ngược sổ điểm.

Người dùng LUÔN thắng dữ liệu: câu trả lời một chạm ghi đè phán quyết mà
verify.py đã chấm từ vệ tinh. Họ đứng trên thửa; ERA5 là ô lưới ~9 km nội suy.
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import _ALGO, _SECRET
from app.db import Alert, Observation, Plot
from app.services import hazard

# Đủ dài để người đi vắng cả tháng vẫn trả lời được, đủ ngắn để một liên kết rò
# rỉ không sống mãi.
TTL_DAYS = 45
_KIND = "tap"

# Ba câu trả lời -> (kết quả cảnh báo, kết quả quan sát)
# "unsure" cố ý KHÔNG chấm điểm: một câu "không rõ" trung thực có giá trị hơn
# một phán quyết bịa, và để đó thì verify.py vẫn còn cơ hội tự chấm từ dữ liệu.
ANSWERS = {
    "yes": ("hit", "occurred"),
    "no": ("false_alarm", "none"),
    "unsure": (None, None),
}


def base_url() -> str:
    """Gốc URL để dựng liên kết. Đặt TERRATWIN_PUBLIC_URL khi deploy thật."""
    return (os.environ.get("TERRATWIN_PUBLIC_URL")
            or "http://localhost:3000").rstrip("/")


def make_token(alert_id: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"a": int(alert_id), "k": _KIND, "iat": now,
         "exp": now + timedelta(days=TTL_DAYS)},
        _SECRET, algorithm=_ALGO)


def read_token(token: str) -> int | None:
    """id cảnh báo, hoặc None nếu chữ ký sai / hết hạn / nhầm loại token.

    Kiểm tra `k == "tap"` là bắt buộc: thiếu nó thì một token đăng nhập bình
    thường cũng lọt qua đây, và tệ hơn — token một chạm sẽ dùng được ở chỗ
    khác nếu chỗ đó chỉ kiểm chữ ký.
    """
    try:
        d = jwt.decode(token, _SECRET, algorithms=[_ALGO])
    except jwt.PyJWTError:
        return None
    if d.get("k") != _KIND:
        return None
    try:
        return int(d["a"])
    except (KeyError, TypeError, ValueError):
        return None


def link_for(alert_id: int) -> str:
    return f"{base_url()}/tap/{make_token(alert_id)}"


def question(a: Alert, db: Session) -> dict:
    """Nội dung câu hỏi cho một cảnh báo — viết bằng tiếng người, không thuật ngữ."""
    ngay = a.created_at.strftime("%d/%m")
    ten = (hazard.name_unit(a.module_id)[0] if hazard.supports(a.module_id)
           else a.module_id)
    plot = db.get(Plot, a.plot_id) if a.plot_id is not None else None
    o_dau = f" thửa {plot.name}" if plot is not None else ""
    # Bỏ tiền tố "Cảnh báo " để câu hỏi đọc xuôi tiếng Việt.
    viec = ten.replace("Cảnh báo ", "").strip() or "hiện tượng này"
    return {
        "alert_id": a.id,
        "module_id": a.module_id,
        "asked_on": ngay,
        "headline": a.headline,
        "question": f"Ngày {ngay} chúng tôi báo {viec}{o_dau}. "
                    f"Thực tế có xảy ra không?",
        "options": [
            {"value": "yes", "label": "Có"},
            {"value": "no", "label": "Không"},
            {"value": "unsure", "label": "Không rõ"},
        ],
        "answered": a.outcome is not None and a.verify_source == "user",
        "outcome": a.outcome,
        "why": ("Câu trả lời của bác được dùng để chỉnh lại ngưỡng cảnh báo cho "
                "chính vùng này. Không hiện tên bác ở đâu cả."),
    }


def answer(a: Alert, value: str, db: Session) -> dict:
    """Ghi nhận câu trả lời. Sinh luôn một quan sát thực địa. KHÔNG commit."""
    if value not in ANSWERS:
        raise ValueError(f"Chỉ nhận: {', '.join(ANSWERS)}.")

    # Đã có người trả lời rồi thì khoá lại. Một liên kết bị chuyển tiếp không
    # được phép lật ngược sổ điểm đã chốt.
    if a.outcome is not None and a.verify_source == "user":
        return {"already": True, "outcome": a.outcome,
                "message": "Cảm ơn bác — câu trả lời trước đã được ghi nhận rồi."}

    alert_outcome, obs_outcome = ANSWERS[value]
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if alert_outcome is None:
        return {"already": False, "outcome": None,
                "message": "Đã ghi nhận “không rõ”. Cảm ơn bác đã trả lời."}

    a.outcome = alert_outcome
    a.verified_at = now
    a.verify_source = "user"          # ghi đè phán quyết từ vệ tinh, có chủ đích
    a.verify_note = (f"Người trên thửa trả lời “"
                     f"{'có' if value == 'yes' else 'không'}” lúc "
                     f"{now.strftime('%d/%m/%Y')}. Câu trả lời của người được "
                     f"ưu tiên hơn số liệu vệ tinh.")

    plot = _record_observation(a, obs_outcome, db, now)
    res = {"already": False, "outcome": a.outcome,
           "message": ("Cảm ơn bác. Câu trả lời này giúp chỉnh ngưỡng cảnh báo "
                       "cho cả vùng.")}
    # M5 — cho người đóng góp THẤY đóng góp có ích: câu này là quan sát thứ mấy ở
    # vùng, còn mấy lần nữa là đủ chỉnh ngưỡng cho cả vùng. Trả lời một chạm mà
    # chỉ nhận "cảm ơn" thì lần sau không ai trả lời — kho quan sát đứng yên.
    if plot is not None:
        res["contribution"] = _contribution(a.module_id, plot, db)
    return res


def _record_observation(a: Alert, obs_outcome: str, db: Session,
                        now: datetime) -> Plot | None:
    """Biến câu trả lời thành một điểm ground-truth cho federated.py.

    Chỉ ghi cho các mô-đun mà tầng hiệu chỉnh hiểu được, và không ghi trùng nếu
    cùng một cảnh báo bị trả lời hai lần. Trả về thửa nếu có GHI (để M5 tính
    đóng góp), None nếu không ghi.
    """
    if not hazard.supports(a.module_id):
        return None
    plot = db.get(Plot, a.plot_id) if a.plot_id is not None else None
    if plot is None:
        return None
    dup = db.execute(
        select(Observation.id).where(Observation.alert_id == a.id)).first()
    if dup:
        return None
    db.add(Observation(
        user_id=a.user_id, plot_id=a.plot_id, lat=plot.lat, lon=plot.lon,
        module_id=a.module_id,
        observed_on=(a.created_at + timedelta(days=(a.window_days or 7) // 2)
                     ).strftime("%Y-%m-%d"),
        outcome=obs_outcome,
        note=f"Trả lời một chạm cho cảnh báo #{a.id}.",
        # Chỉ số model lúc phát cảnh báo. Có `observed_peak` thì dùng, không thì
        # suy từ mức đã báo — federated.py chỉ cần biết model có báo (≥40) hay không.
        model_index=(a.observed_peak if a.observed_peak is not None
                     else (75.0 if a.risk_level == "danger" else 50.0)),
        source="onetap", alert_id=a.id, created_at=now))
    return plot


def _contribution(module_id: str, plot: Plot, db: Session) -> dict:
    """M5 — câu trả lời vừa rồi là quan sát thứ mấy ở VÙNG (ô lưới 0,5°), và còn
    mấy lần nữa là đủ để hiệu chỉnh ngưỡng cho cả vùng. Số thật từ federated.

    Đếm theo ô lưới 0,5° (giống federated.cell_of) — làm tròn xuống nên không lộ
    toạ độ thửa cụ thể của ai.
    """
    from app.services import federated

    db.flush()      # để đếm GỒM cả quan sát vừa thêm (chưa commit)
    g = federated.GRID
    glat = math.floor(plot.lat / g) * g
    glon = math.floor(plot.lon / g) * g
    n = db.execute(
        select(func.count(Observation.id)).where(
            Observation.module_id == module_id,
            Observation.lat >= glat, Observation.lat < glat + g,
            Observation.lon >= glon, Observation.lon < glon + g)
    ).scalar_one()
    remaining = max(0, federated.MIN_OBS - n)
    if remaining > 0:
        msg = (f"Câu trả lời của bác là quan sát thứ {n} ở vùng này. Còn "
               f"{remaining} lần nữa là TerraTwin chỉnh được ngưỡng cho cả vùng.")
    else:
        msg = (f"Vùng này đã đủ {n} quan sát — ngưỡng đang được hiệu chỉnh cho "
               f"cả vùng nhờ những câu trả lời như của bác.")
    return {"count_in_region": int(n), "min_needed": federated.MIN_OBS,
            "remaining": remaining, "enough": remaining == 0, "message": msg}


def pending_questions(db: Session, user_id: int, limit: int = 5) -> list[dict]:
    """Câu hỏi đang chờ người này trả lời — để hiện trong app, không chỉ trong
    tin nhắn. Người không bật thông báo vẫn phải có đường đóng vòng lặp."""
    from app.services import active
    from app.services.verify import SETTLE_DAYS
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # Lấy DƯ ứng viên để còn xếp hạng, không chỉ cắt theo thời gian.
    rows = db.execute(
        select(Alert).where(
            Alert.user_id == user_id, Alert.retro == 0,
            Alert.verify_source != "user",
            Alert.created_at <= now - timedelta(days=SETTLE_DAYS))
        .order_by(Alert.created_at.desc()).limit(max(1, limit) * 6)
    ).scalars().all()

    # A12 — hỏi câu ĐÁNG HỎI NHẤT chứ không phải mới nhất: xếp theo học chủ động
    # (phân vân + đói dữ liệu vùng + bất đồng tầng). Số lần được hỏi là tài
    # nguyên khan hiếm nhất, không tiêu ngẫu nhiên.
    eligible = [a for a in rows
                if a.created_at + timedelta(days=a.window_days or 7) <= now]
    scored = [(active.value_of_asking(a, db), a) for a in eligible]
    scored.sort(key=lambda x: x[0], reverse=True)

    out = []
    for score, a in scored[:limit]:
        q = question(a, db)
        q["token"] = make_token(a.id)
        q["ask_value"] = score      # công khai điểm để đo học-chủ-động vs ngẫu nhiên
        out.append(q)
    return out

"""Tầng database — SQLAlchemy 2.0.

Mặc định SQLite (chạy được ngay, không cần cài gì). Đặt TERRATWIN_DATABASE_URL
để chuyển sang PostgreSQL/PostGIS khi lên production — code không đổi.

Bảng:
  users        — tài khoản
  plots        — thửa đất đã lưu (thay localStorage, để bán được B2B)
  api_keys     — khóa cho Twin API (C12)
  datasets     — dữ liệu người dùng tự tải lên (C11 Bring-Your-Own-Data)
  kv_cache     — cache bền cho lấy mẫu lưới (C06 Heatmap, S04 Twin Genome)
  alerts       — nhật ký cảnh báo do Proactive Radar sinh ra (C05/S08)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker,
)

def normalize_url(url: str) -> str:
    """Render (và Neon, Heroku, Supabase…) cấp URL dạng postgresql:// hoặc
    postgres://. SQLAlchemy mặc định lái cả hai sang psycopg2 — nhưng ta chỉ cài
    psycopg (v3), nên backend sẽ chết ngay khi mở kết nối: ModuleNotFoundError:
    psycopg2. Chuẩn hoá về +psycopg để dùng đúng driver đã cài, bất kể nơi cấp
    URL viết kiểu gì. Không đụng tới sqlite hay URL đã ghi rõ driver.

    CHỈ thay tiền tố — phần query (?sslmode=require&channel_binding=require của
    Neon) phải đi nguyên vẹn tới libpq; mất sslmode là kết nối bị Neon từ chối."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def connect_args_for(url: str) -> dict:
    """Tham số driver theo loại CSDL.

    Neon: dùng URL Direct. URL "-pooler" đi qua PgBouncer chế độ transaction,
    mà psycopg 3 tự chuẩn bị (prepare) câu lệnh chạy lặp từ lần thứ 5 — câu đã
    prepare nằm ở MỘT kết nối máy chủ, lần sau PgBouncer đưa sang kết nối khác
    → lỗi 'prepared statement "_pg3_0" does not exist'. Lỡ dùng pooler thì tắt
    prepare (prepare_threshold=None) thay vì hỏng ngẫu nhiên lúc có tải."""
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    if "-pooler." in url:
        return {"prepare_threshold": None}
    return {}


DATABASE_URL = normalize_url(
    os.environ.get("TERRATWIN_DATABASE_URL", "sqlite:///./terratwin.db"))

_connect_args = connect_args_for(DATABASE_URL)
# pool_pre_ping: Neon gói miễn phí tắt compute sau ~5 phút không truy vấn, và
# api gói free của Render ngủ/thức — kết nối nằm trong pool lúc đó đã chết.
# Ping trước khi dùng thì SQLAlchemy tự mở kết nối mới, thay vì trả lỗi
# "SSL connection has been closed unexpectedly" cho request đầu tiên.
engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True,
                       pool_pre_ping=not DATABASE_URL.startswith("sqlite"))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _alert_env() -> str:
    """Môi trường tạo cảnh báo. Chạy dev đặt TERRATWIN_ENV=dev để cảnh báo thử
    không lẫn vào sổ điểm công khai; production để trống → "prod"."""
    return os.environ.get("TERRATWIN_ENV", "prod").strip().lower() or "prod"


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(120), default="")
    # Đ11 — phân quyền: "user" (mặc định) · "coop" (hợp tác xã, xem cả nhóm) ·
    # "admin" (xem trang vận hành). Route /api/admin/* chỉ mở cho admin.
    role: Mapped[str] = mapped_column(String(16), default="user", server_default="user")
    # M4 — bản tin sáng: mặc định TẮT (người dùng tự bật để không spam). brief_last
    # giữ ngày gửi gần nhất (YYYY-MM-DD) để không gửi trùng trong cùng buổi sáng.
    morning_brief: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    brief_last: Mapped[str] = mapped_column(String(10), default="", server_default="")
    # N1 — email CHƯA XÁC THỰC vẫn dùng app bình thường (lưu thửa, xem cảnh
    # báo trong app), nhưng KHÔNG được gửi cảnh báo ra kênh ngoài (email/Zalo/
    # Telegram/webhook) thay họ — một địa chỉ gõ sai hoặc tài khoản bot tạo
    # hàng loạt không được phép biến TerraTwin thành máy gửi thư rác hộ.
    email_verified: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # N8 — đồng ý TÁCH TỪNG MỤC ĐÍCH, không phải một ô "đồng ý điều khoản" gộp
    # hết. Ba mục KHÁC NHAU về mức nhạy cảm nên mặc định khác nhau:
    #   consent_alerts        — gửi cảnh báo ra kênh đã nối. Mặc định BẬT: đây
    #                            là lý do chính người dùng đăng ký, tắt mặc
    #                            định là phá chức năng cốt lõi ngay từ đầu.
    #   consent_observations  — dùng quan sát thực địa (đã ẩn danh, làm tròn
    #                            về ô ~55 km, xem /privacy) để hiệu chỉnh
    #                            ngưỡng CHUNG cho cả vùng. Mặc định BẬT: đây
    #                            là cách duy nhất mô hình tốt lên, và dữ liệu
    #                            đã ẩn danh trước khi dùng.
    #   consent_research      — dùng cho nghiên cứu/xuất bản rộng hơn hiệu
    #                            chỉnh vận hành. Mặc định TẮT — người dùng tự
    #                            bật, đây là mục đích RỘNG NHẤT nên đòi hỏi rõ
    #                            ràng nhất.
    consent_alerts: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    consent_observations: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    consent_research: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Đ11 — vai trò "coop" cần biết THÀNH VIÊN NÀO CÙNG NHÓM và AI ĐỒNG Ý cho
    # xem. coop_code là chuỗi bất kỳ người dùng tự đặt để "vào cùng nhóm" với
    # người khác gõ đúng chuỗi đó (không có bảng Nhóm riêng — cố tình đơn giản,
    # một HTX thật thường chỉ vài chục người, chuỗi chung đủ dùng). Rỗng =
    # chưa vào nhóm nào, coop KHÔNG thấy người này dù role='coop' đọc được.
    # share_with_coop TÁCH RIÊNG khỏi coop_code: đặt mã nhóm không có nghĩa là
    # đồng ý lộ thửa — phải bật rõ ràng, mặc định TẮT (giống consent_research,
    # đây cũng là mục đích RỘNG lộ toạ độ cho người khác ngoài chủ thửa).
    coop_code: Mapped[str] = mapped_column(String(64), default="", server_default="")
    share_with_coop: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    plots: Mapped[list["Plot"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan")


class Plot(Base):
    """Thửa đất người dùng lưu. Thay hoàn toàn localStorage."""
    __tablename__ = "plots"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    area_ha: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Ảnh chụp TerraScore lúc lưu — để so sánh danh mục mà không phải gọi lại API.
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grade: Mapped[str | None] = mapped_column(String(4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    owner: Mapped[User] = relationship(back_populates="plots")

    __table_args__ = (
        # Một người không lưu trùng cùng một toạ độ hai lần.
        UniqueConstraint("user_id", "lat", "lon", name="uq_plot_user_coord"),
    )


class Twin(Base):
    """C01 Twin Builder — bản sao số của một thửa đất, đã dựng và lưu lại.

    Khác `Plot` (chỉ là toạ độ đã lưu): Twin chứa TẤT CẢ các lớp dữ liệu đã
    dựng tại một thời điểm — địa hình, khí hậu, hiểm họa, TerraScore — nên xem
    lại được nguyên trạng mà không phải gọi lại toàn bộ API.
    """
    __tablename__ = "twins"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plot_id: Mapped[int | None] = mapped_column(
        ForeignKey("plots.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    area_ha: Mapped[float | None] = mapped_column(Float, nullable=True)
    layers: Mapped[str] = mapped_column(Text)          # JSON các lớp đã dựng
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grade: Mapped[str | None] = mapped_column(String(4), nullable=True)
    built_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class NotifyChannel(Base):
    """U01 Action & Automation — nơi gửi cảnh báo tới."""
    __tablename__ = "notify_channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # webhook | email | zalo | telegram
    #
    # Zalo và Telegram thêm sau, vì phép đo phơi ra một lỗ hổng chí mạng: radar
    # chạy đều 6 giờ một lần, sinh hàng trăm cảnh báo, mà KHÔNG cảnh báo nào có
    # đường tới điện thoại một người làm ruộng. Webhook là thứ của lập trình
    # viên; email không phải kênh của nông dân Việt Nam. Zalo mới là kênh thật.
    kind: Mapped[str] = mapped_column(String(16))
    target: Mapped[str] = mapped_column(String(500))    # URL hoặc địa chỉ email
    # Chỉ gửi khi mức rủi ro đạt ngưỡng này trở lên.
    min_level: Mapped[str] = mapped_column(String(16), default="warning")
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Observation(Base):
    """S05 Federated Learning — quan sát THỰC ĐỊA do người dùng gửi.

    Đây là moat của TerraTwin. Mô hình chạy trên dữ liệu vệ tinh mở mà ai cũng
    có; thứ không ai copy được là "hôm 12/10 ruộng tôi ngập thật". Mỗi quan sát
    là một điểm ground-truth để hiệu chỉnh ngưỡng cho vùng đó.

    "Federated" ở đây có nghĩa cụ thể: quan sát THÔ gắn với tài khoản người gửi
    và không bao giờ lộ ra ngoài. Thứ được chia sẻ giữa mọi người chỉ là con số
    hiệu chỉnh tổng hợp theo vùng — xem services/federated.py.
    """
    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plot_id: Mapped[int | None] = mapped_column(
        ForeignKey("plots.id", ondelete="SET NULL"), nullable=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    module_id: Mapped[str] = mapped_column(String(48), index=True)
    # Ngày sự kiện xảy ra ngoài đồng (không phải ngày gửi).
    observed_on: Mapped[str] = mapped_column(String(10), index=True)
    # occurred = có xảy ra thật; none = model báo nhưng KHÔNG xảy ra (báo động giả)
    outcome: Mapped[str] = mapped_column(String(16))
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    # Chỉ số model tính cho chính ngày đó — chốt lại lúc gửi để chấm điểm sau.
    model_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    # user   = tự vào phần mềm gõ (đòi đăng nhập)
    # onetap = trả lời một chạm ngay trong tin nhắn cảnh báo, KHÔNG đăng nhập
    #
    # Phân biệt hai nguồn này là cần thiết chứ không phải để thống kê cho vui:
    # bắt một người nông dân lập tài khoản trước khi họ được phép nói cho ta
    # biết ruộng đã ngập là điểm chết của cả vòng lặp. Đo được tỉ lệ giữa hai
    # nguồn thì mới biết đường một chạm có thật sự gánh việc hay không.
    source: Mapped[str] = mapped_column(String(16), default="user", index=True)
    # Quan sát này trả lời cho cảnh báo nào (nếu đến từ đường một chạm).
    alert_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class ActionLog(Base):
    """U04 Autonomous Closed-Loop — vòng khép kín với NGƯỜI là cơ cấu chấp hành.

    Không có van bơm IoT, nhưng vòng vẫn đóng được: hệ thống khuyến nghị →
    người xác nhận đã làm → hệ thống đối chiếu kết quả về sau. Mắt xích thường
    bị bỏ qua chính là mắt xích cuối: hầu hết phần mềm cảnh báo không bao giờ
    biết lời khuyên của nó có ai làm theo không, và có hiệu quả không.
    """
    __tablename__ = "action_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    alert_id: Mapped[int | None] = mapped_column(
        ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True)
    plot_id: Mapped[int | None] = mapped_column(
        ForeignKey("plots.id", ondelete="SET NULL"), nullable=True)
    module_id: Mapped[str] = mapped_column(String(48))
    recommendation: Mapped[str] = mapped_column(Text)
    # done = đã làm theo · skipped = bỏ qua · other = làm cách khác
    status: Mapped[str] = mapped_column(String(16), default="done")
    note: Mapped[str] = mapped_column(Text, default="")
    acted_on: Mapped[str] = mapped_column(String(10))
    # Kết quả đối chiếu về sau, do người dùng xác nhận.
    outcome: Mapped[str | None] = mapped_column(String(24), nullable=True)
    outcome_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class KnowledgeNote(Base):
    """U02 Marketplace — chợ TRI THỨC, không phải chợ tiền.

    Ghép theo Twin Genome: kinh nghiệm của người có bộ gen đất giống bạn đáng
    học hơn kinh nghiệm chung chung. Không thanh toán nên không vướng pháp lý.
    """
    __tablename__ = "knowledge_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    topic: Mapped[str] = mapped_column(String(48), index=True)
    author_name: Mapped[str] = mapped_column(String(120), default="")
    helpful_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class ApiKey(Base):
    """C12 Twin API — khóa để bên thứ ba gọi API thay cho JWT."""
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(120), default="")
    # Chỉ lưu HASH của khóa — lộ database vẫn không dùng được khóa.
    key_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    prefix: Mapped[str] = mapped_column(String(16))     # để người dùng nhận ra khóa nào
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked: Mapped[int] = mapped_column(Integer, default=0)
    # Đếm lượt dùng. Đây KHÔNG phải để tính tiền (chưa có cổng thanh toán) mà
    # để CHỐNG LẠM DỤNG: một khóa bị lộ có thể nã API không giới hạn và đốt sạch
    # hạn mức ngày của Open-Meteo — lúc đó MỌI người dùng mất dữ liệu, không
    # riêng chủ khóa. Hạn mức theo tháng cũng là điều kiện cần cho mô hình "trả
    # theo lượt gọi" sau này.
    calls_total: Mapped[int] = mapped_column(Integer, default=0)
    calls_period: Mapped[int] = mapped_column(Integer, default=0)
    period: Mapped[str] = mapped_column(String(7), default="")   # YYYY-MM
    # Gói cước quyết định hạn mức tháng. Để ở KHÓA chứ không ở NGƯỜI DÙNG, vì
    # một người có thể có khóa cho việc khác nhau — khóa thử nghiệm để gói thấp,
    # khóa chạy thật để gói cao, và một khóa bị lộ không kéo theo cả tài khoản.
    plan: Mapped[str] = mapped_column(String(16), default="free")


class Dataset(Base):
    """C11 Bring-Your-Own-Data — dữ liệu người dùng tự tải lên."""
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(32))       # points | geojson | csv
    payload: Mapped[str] = mapped_column(Text)          # JSON đã chuẩn hoá
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class KVCache(Base):
    """Cache BỀN qua nhiều tiến trình — cache in-memory vỡ khi chạy nhiều worker.

    Cần cho C06 Heatmap và S04 Twin Genome: lấy mẫu lưới hàng trăm điểm sẽ
    vượt rate limit Open-Meteo nếu mỗi lần đều gọi lại.
    """
    __tablename__ = "kv_cache"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class Alert(Base):
    """C05 Proactive Radar / S08 Autonomous Agent — nhật ký cảnh báo đã phát."""
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plot_id: Mapped[int | None] = mapped_column(
        ForeignKey("plots.id", ondelete="CASCADE"), nullable=True, index=True)
    module_id: Mapped[str] = mapped_column(String(48))
    risk_level: Mapped[str] = mapped_column(String(16))
    headline: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    acknowledged: Mapped[int] = mapped_column(Integer, default=0)

    # ---- SỔ ĐIỂM TỰ CHẤM (services/verify.py) ----
    #
    # VÌ SAO CÓ: trước đây bảng này chỉ ghi "đã báo gì", không bao giờ ghi "báo
    # có đúng không". Phần mềm chứng minh được nó SẼ bắt được lũ Huế 2020 (nhờ
    # backtest trên danh sách sự kiện lịch sử chọn sẵn) nhưng chưa từng kiểm tra
    # một cái nào trong hàng trăm cảnh báo của CHÍNH NÓ. Mô hình hôm nay và mô
    # hình sau một năm vì thế là một — không có đường nào để tự tốt lên.
    #
    # Sáu cột dưới đóng vòng lặp đó. Chúng cố ý lưu cả BẰNG CHỨNG
    # (`observed_peak`, `verify_note`) chứ không chỉ kết luận, để người ngoài
    # kiểm tra lại được phán quyết thay vì phải tin.
    #
    # outcome: hit | miss | false_alarm | expired   (None = chưa tới hạn chấm)
    outcome: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # data = tự chấm từ số liệu thực đo; user = người dùng trả lời một chạm.
    # Người dùng LUÔN thắng dữ liệu: họ đứng trên thửa, vệ tinh thì không.
    verify_source: Mapped[str] = mapped_column(String(16), default="")
    verify_note: Mapped[str] = mapped_column(Text, default="")
    observed_peak: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Cửa sổ cảnh báo nhìn tới mấy ngày — quyết định khi nào được phép chấm.
    window_days: Mapped[int] = mapped_column(Integer, default=7)
    # 1 = bản ghi HỒI CỨU: hiểm họa đã thực sự xảy ra mà phần mềm KHÔNG hề báo.
    #
    # Phải có, nếu không sổ điểm sẽ tự khen mình. Chỉ đếm những cảnh báo đã phát
    # thì mọi lần bỏ sót đều vô hình, và "độ chính xác" đo được sẽ chỉ là tỉ lệ
    # báo đúng trên số lần dám báo — một con số đẹp và vô nghĩa. Hàng `retro=1`
    # KHÔNG bao giờ hiện trong danh sách cảnh báo của người dùng (chưa từng gửi
    # cho họ) nhưng LUÔN được tính vào sổ điểm.
    retro: Mapped[int] = mapped_column(Integer, default=0, index=True)
    # dev = cảnh báo sinh trong GIAI ĐOẠN PHÁT TRIỂN (toạ độ thử, radar test lúc
    # dev); prod = cảnh báo thật sau khi phát hành. Sổ điểm CÔNG KHAI chỉ tính
    # prod và ghi rõ đã loại bao nhiêu bản dev — loại trừ CÓ LÝ DO, không phải
    # xoá lén. Giá trị khi tạo lấy từ TERRATWIN_ENV (mặc định "prod").
    env: Mapped[str] = mapped_column(String(8), default=_alert_env,
                                     server_default="prod", index=True)


Index("ix_alert_user_created", Alert.user_id, Alert.created_at.desc())
# Sổ điểm luôn quét theo "đã chấm chưa" + "chấm lúc nào".
Index("ix_alert_outcome_time", Alert.outcome, Alert.created_at.desc())
# Đ4 — gộp kết quả theo ĐỢT (scorecard._deduped_counts) và quét bỏ sót
# (verify._record_misses) đều lọc/nhóm theo (thửa, mô-đun, thời gian). Không có
# index này thì mỗi lần chấm quét toàn bảng alerts.
Index("ix_alert_plot_module_time", Alert.plot_id, Alert.module_id, Alert.created_at)


class Event(Base):
    """N6 — đếm sự kiện ẨN DANH phía máy chủ, để biết người dùng rơi rụng ở đâu.

    KHÔNG lưu id người dùng, KHÔNG lưu IP — chỉ tên sự kiện + thời điểm + ít
    meta không định danh. Vì thế không đụng Nghị định 13 và không cần xin phép
    cookie. Không có đo lường này thì mọi quyết định cải tiến về sau là ĐOÁN:
    không biết bao nhiêu người bỏ giữa lúc quét, bao nhiêu người cuộn tới sổ
    điểm, bao nhiêu người bấm liên kết một chạm rồi thoát.
    """
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    name: Mapped[str] = mapped_column(String(32), index=True)
    meta_json: Mapped[str] = mapped_column(Text, default="")


class AuditLog(Base):
    """Đ12 — nhật ký kiểm toán các HÀNH ĐỘNG NHẠY CẢM lên một tài khoản.

    Khác Event (đếm ẩn danh, không biết ai): audit gắn với user_id để chính chủ
    xem được "tài khoản mình đã bị/được làm gì" — đăng nhập, đổi/đặt lại mật
    khẩu, tạo/thu hồi khoá API. Đây vừa là an ninh (chủ nhà thấy hoạt động lạ)
    vừa là điều kiện làm việc với cơ quan nhà nước theo Nghị định 13. KHÔNG lưu
    IP đầy đủ — chỉ hành động + thời điểm + mô tả ngắn không định danh bên thứ ba.
    """
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    detail: Mapped[str] = mapped_column(String(200), default="")


class PushSub(Base):
    """M1 — đăng ký nhận thông báo đẩy Web Push của một trình duyệt/thiết bị.

    endpoint là URL push riêng của trình duyệt (duy nhất); p256dh + auth là khoá
    mã hoá payload theo RFC 8291. Một người dùng có thể có nhiều đăng ký (nhiều
    thiết bị). Endpoint chết (404/410) thì xoá để không gửi mãi vào chỗ trống.
    """
    __tablename__ = "push_subs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Job(Base):
    """Đ10 — hàng đợi việc dài BỀN, thay hàng đợi trong bộ nhớ (jobs.py).

    jobs.py (in-RAM) mất sạch việc đang chờ mỗi lần restart, và không chia sẻ
    được giữa nhiều tiến trình worker (Render có thể chạy >1 instance). Bảng
    này giải đúng hai vấn đề đó — dùng SELECT...FOR UPDATE SKIP LOCKED để
    NHIỀU worker cùng đọc bảng mà không tranh nhau một việc (xem services/
    jobs_db.py). `args_json`/`result_json` bắt buộc phải TUẦN TỰ HOÁ ĐƯỢC
    (JSON) — khác jobs.py cũ nhận thẳng một closure Python, không thể lưu
    xuống database được. Đây LÀ lý do phải có một bảng REGISTRY ánh xạ `kind`
    → hàm xử lý (xem jobs_db.register()), thay vì truyền thẳng hàm.
    """
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(255), default="")
    args_json: Mapped[str] = mapped_column(Text, default="{}")
    # queued | running | done | error
    state: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Tiến độ trong lúc chạy (vd {"done": 2, "total": 3, "current": "Huế"}) —
    # việc dài vài phút mà giao diện chỉ hiện "đang chạy…" thì người dùng
    # tưởng treo và bấm lại.
    progress_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ModelVersion(Base):
    """A6 — SỔ ĐĂNG KÝ MÔ HÌNH + quay lui.

    Có A1 (U-Net) và A11 (TCN) mà không có sổ này thì sau ba tháng không ai biết
    mô hình nào đang chạy, huấn luyện từ dữ liệu nào, và vì sao hôm nay tệ hơn
    tháng trước. Mỗi lần huấn luyện ghi một hàng kèm MÃ BĂM bộ dữ liệu — không có
    nó thì 'mô hình này huấn luyện từ đâu' là câu không trả lời được. Đổi mô hình
    đang hoạt động bằng một lời gọi API, không cần deploy lại; quay lui cũng vậy.
    """
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)   # vd "landcover", "tcn_flood"
    version: Mapped[str] = mapped_column(String(40))
    trained_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    data_hash: Mapped[str] = mapped_column(String(64), default="")
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    artifact_path: Mapped[str] = mapped_column(String(255), default="")
    active: Mapped[int] = mapped_column(Integer, default=0, index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class SigningKey(Base):
    """Khoá ký Hồ sơ đất số (Ed25519). Giữ MỌI khoá công khai từng dùng — đổi khoá
    thì hồ sơ phát hành bằng khoá cũ vẫn kiểm được. `private_b64` chỉ có khi khoá
    được TỰ SINH (chưa đặt TERRATWIN_SIGNING_KEY); khoá từ biến môi trường không
    bao giờ ghi phần bí mật xuống đây."""
    __tablename__ = "signing_keys"

    key_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    public_b64: Mapped[str] = mapped_column(String(64))
    private_b64: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="auto")   # "env" | "auto"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Dossier(Base):
    """Hồ sơ đất số đã PHÁT HÀNH — sổ đăng ký CHỈ GHI THÊM, móc xích băm.

    Mỗi hồ sơ: nội dung (facts_json, đóng băng lúc phát hành) → facts_hash;
    entry_hash = sha256(seq|id|thời điểm|facts_hash|prev_hash) nối vào hồ sơ
    trước (prev_hash) như Certificate Transparency: sửa hay xoá một hồ sơ cũ là
    gãy mọi mắt xích sau nó. entry_hash được ký Ed25519 bằng khoá của máy chủ —
    kẻ sửa nội dung tự băm lại được, nhưng KHÔNG tự ký lại được.
    """
    __tablename__ = "dossiers"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)   # mã công khai, ngẫu nhiên
    seq: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    # Không khoá ngoại: xoá tài khoản không được làm gãy sổ đăng ký công khai.
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    facts_json: Mapped[str] = mapped_column(Text)
    # Tiết lộ chọn lọc: {trường: {salt, value}} — KHÔNG công khai, chỉ chủ hồ sơ (đăng
    # nhập) đọc được; nội dung đã ký chỉ chứa mã băm có muối (services/disclosure.py).
    private_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    facts_hash: Mapped[str] = mapped_column(String(64))
    prev_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64), unique=True)
    signature: Mapped[str] = mapped_column(String(128))
    key_id: Mapped[str] = mapped_column(String(16))


class BatchRun(Base):
    """Một lần THẨM ĐỊNH HÀNG LOẠT (CSV nhiều thửa) — lưu kết quả lâu dài.

    Hàng đợi việc (bảng jobs) dọn kết quả sau 30 phút; ngân hàng/hợp tác xã cần
    mở lại danh mục đã thẩm định tuần trước, nên kết quả được chép sang đây khi
    xong. rows_json/summary_json đóng băng lúc chạy — muốn số mới thì chạy lại.
    """
    __tablename__ = "batch_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)    # = job_id
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    title: Mapped[str] = mapped_column(String(200), default="")
    n_rows: Mapped[int] = mapped_column(Integer, default=0)        # số thửa ĐÃ GỬI
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    rows_json: Mapped[str] = mapped_column(Text, default="[]")       # kết quả TỪNG thửa, ghi dần
    # queued | running | done — ghi kết quả sau MỖI thửa để máy chủ chết giữa lô
    # thì chạy tiếp được từ thửa dở (services/batch.py, jobs_db.requeue_running).
    state: Mapped[str] = mapped_column(String(12), default="done")


class FieldPhoto(Base):
    """Ảnh thực địa gửi kèm Hồ sơ đất số, ĐÃ KIỂM (services/evidence.py).

    Chỉ lưu ẢNH THU NHỎ đã xoá EXIF (không lưu bản gốc: CSDL miễn phí 0,5 GB và
    EXIF gốc mang thông tin thiết bị) + SHA-256 của bản gốc + băm cảm quan dHash
    để bắt ảnh dùng lại cho thửa khác. Toạ độ GPS của ảnh chỉ giữ để tính lại
    khoảng cách — không trả ra ngoài.
    """
    __tablename__ = "field_photos"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    plot_lat: Mapped[float] = mapped_column(Float)
    plot_lon: Mapped[float] = mapped_column(Float)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    phash: Mapped[str] = mapped_column(String(16), index=True)
    gps_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    verdict: Mapped[str] = mapped_column(String(12))            # match | review | mismatch
    checks_json: Mapped[str] = mapped_column(Text, default="[]")
    thumb: Mapped[bytes] = mapped_column(LargeBinary)
    thumb_sha256: Mapped[str] = mapped_column(String(64))
    dossier_id: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)


class LogHead(Base):
    """ĐẦU CÂY ĐÃ KÝ (signed tree head) của sổ minh bạch — RFC 6962.

    Một dòng cho mỗi kích thước cây từng công bố: gốc Merkle của mọi entry_hash hồ
    sơ từ #1 tới #tree_size, thời điểm, chữ ký Ed25519. Bên thứ ba lưu các đầu cây
    này (tác vụ GitHub Actions neo ra nhánh transparency-log) và đòi bằng chứng nhất
    quán giữa hai đầu cây — sổ bị sửa ngược là lộ.
    """
    __tablename__ = "log_heads"

    tree_size: Mapped[int] = mapped_column(Integer, primary_key=True)
    root_hash: Mapped[str] = mapped_column(String(64))
    timestamp: Mapped[str] = mapped_column(String(32))
    signature: Mapped[str] = mapped_column(String(128))
    key_id: Mapped[str] = mapped_column(String(16))


class Lot(Base):
    """LÔ HÀNG: các đợt nhập từ từng vườn (mã hồ sơ EUDR + số kg) → kiểm cân bằng
    khối lượng → CHỨNG THƯ LÔ HÀNG (gốc Merkle của các hồ sơ vườn, phát hành như một
    hồ sơ trong sổ móc xích — xem services/lots.py)."""
    __tablename__ = "lots"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    ref: Mapped[str] = mapped_column(String(80), default="")
    commodity: Mapped[str] = mapped_column(String(24), default="coffee")
    season: Mapped[str] = mapped_column(String(16), default="")
    operator: Mapped[str] = mapped_column(String(160), default="")
    deliveries_json: Mapped[str] = mapped_column(Text, default="[]")
    checks_json: Mapped[str] = mapped_column(Text, default="{}")
    state: Mapped[str] = mapped_column(String(12), default="draft")      # draft | certified
    certificate_id: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)


class DossierMonitor(Base):
    """GIÁM SÁT SAU PHÁT HÀNH: lần sàng lọc lại một hồ sơ vườn EUDR bằng dữ liệu mới.
    KHÔNG sửa hồ sơ đã ký (bất biến) — ghi thêm ở đây, trang kiểm hiện kèm, nhãn rõ
    là kết quả sống, không phải nội dung đã ký."""
    __tablename__ = "dossier_monitors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dossier_id: Mapped[str] = mapped_column(String(16), index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    level: Mapped[str] = mapped_column(String(12))
    issued_level: Mapped[str] = mapped_column(String(12))
    changed: Mapped[int] = mapped_column(Integer, default=0)
    summary_json: Mapped[str] = mapped_column(Text, default="{}")


class EudrSet(Base):
    """Một LÔ THỬA kiểm theo EUDR (doanh nghiệp, hợp tác xã tải tệp ranh thửa lên).

    plots_json: thửa đã chuẩn hoá + vấn đề chuẩn EU (services/eudr_geo.py), đóng
    băng lúc gửi. results_json: {chỉ số thửa: kết quả sàng lọc} GHI DẦN sau mỗi thửa
    (máy chủ miễn phí ngủ giữa chừng thì chạy tiếp được từ thửa dở, như batch_runs).
    """
    __tablename__ = "eudr_sets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)    # = job_id
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    title: Mapped[str] = mapped_column(String(200), default="")
    commodity: Mapped[str] = mapped_column(String(24), default="")
    producer: Mapped[str] = mapped_column(String(120), default="")
    n_plots: Mapped[int] = mapped_column(Integer, default=0)
    plots_json: Mapped[str] = mapped_column(Text, default="[]")
    results_json: Mapped[str] = mapped_column(Text, default="{}")
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    state: Mapped[str] = mapped_column(String(12), default="queued")   # queued | running | done



class Device(Base):
    """Thiết bị IoT tại vườn (trạm đo ẩm đất, mưa, nhiệt…) — NHẬN DẠNG BẰNG KHOÁ CÔNG KHAI.

    Thiết bị tự sinh khoá Ed25519; khoá bí mật KHÔNG BAO GIỜ rời thiết bị, máy chủ chỉ
    giữ public_b64. Vì vậy cả máy chủ cũng không giả được số liệu "của thiết bị": mọi số
    đo phải mang chữ ký kiểm được bằng khoá công khai này. kind="simulator" là thiết bị
    giả lập để demo — luôn hiện nhãn, không bao giờ lẫn với số đo thật.
    """
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    name: Mapped[str] = mapped_column(String(80), default="")
    kind: Mapped[str] = mapped_column(String(16), default="sensor")      # sensor | simulator
    public_b64: Mapped[str] = mapped_column(String(64), unique=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    dossier_id: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    last_seq: Mapped[int] = mapped_column(Integer, default=0)            # chống phát lại
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked: Mapped[int] = mapped_column(Integer, default=0)


class SensorReading(Base):
    """Một số đo ĐÃ KÝ của thiết bị. Lưu nguyên chuỗi đã ký + chữ ký để BẤT KỲ AI cũng
    kiểm lại được bằng khoá công khai của thiết bị — không cần tin máy chủ."""
    __tablename__ = "sensor_readings"
    __table_args__ = (UniqueConstraint("device_id", "seq", name="uq_reading_device_seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(16), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    measured_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    metrics_json: Mapped[str] = mapped_column(Text)
    signed: Mapped[str] = mapped_column(Text)            # chuỗi canonical đúng như đã ký
    signature: Mapped[str] = mapped_column(String(96))


class PilotFeedback(Base):
    """Một phiếu góp ý thí điểm (trên web, hoặc cán bộ HTX nhập lại từ phiếu giấy).

    ÍT DỮ LIỆU CÁ NHÂN NHẤT (Nghị định 13/2023): không lưu IP, không bắt buộc tên.
    `contact` chỉ được lưu khi người gửi tự đánh dấu đồng ý cho liên hệ lại — không đồng
    ý thì API từ chối cả phiếu có liên hệ, không lặng lẽ lưu."""
    __tablename__ = "pilot_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    source: Mapped[str] = mapped_column(String(8), default="web")       # web | paper
    role: Mapped[str] = mapped_column(String(16))                      # farmer | coop | exporter | other
    region: Mapped[str] = mapped_column(String(80), default="")
    hardest: Mapped[str] = mapped_column(String(16), default="none")   # bước khó nhất
    ease: Mapped[int] = mapped_column(Integer)                         # 1–5
    trust: Mapped[int] = mapped_column(Integer)                        # 1–5
    minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    would_use: Mapped[str] = mapped_column(String(8))                  # yes | maybe | no
    comment: Mapped[str] = mapped_column(Text, default="")
    contact: Mapped[str] = mapped_column(String(120), default="")
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class LabelV3(Base):
    """Một nhãn do NGƯỜI gán cho một ô của mẫu kiểm định EUDR v3 (giải đoán ảnh 2020).

    Mỗi người gán một nhãn / ô (sửa được tới khi khoá). Hai người gán ĐỘC LẬP: API không
    bao giờ trả nhãn của người khác, kết quả bản đồ hay mô hình cho người đang gán."""
    __tablename__ = "labels_v3"
    __table_args__ = (UniqueConstraint("cell", "user_id", name="uq_label_v3_cell_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cell: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    cover2020: Mapped[str] = mapped_column(String(16))     # natural_forest|planted_forest|tree_crop|no_trees|unclear
    loss: Mapped[str] = mapped_column(String(8))           # yes|no|unclear — mất tán cây SAU 31/12/2020
    confidence: Mapped[int] = mapped_column(Integer, default=2)   # 1 đoán · 2 khá chắc · 3 chắc
    seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str] = mapped_column(String(300), default="")


class LabelerGrant(Base):
    """Quản trị viên cấp quyền gán nhãn cho một email (người thứ hai không cần là admin)."""
    __tablename__ = "labeler_grants"

    email: Mapped[str] = mapped_column(String(254), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    granted_by: Mapped[int | None] = mapped_column(Integer, nullable=True)

# Cột thêm sau khi đã có database chạy thật. `create_all` KHÔNG thêm cột vào
# bảng sẵn có, nên thiếu bước này thì bản deploy cũ sẽ đổ ngay lần truy vấn đầu
# — lỗi chỉ lộ ra ở production, không bao giờ lộ trong test trên database sạch.
#
# KIỂU PHẢI VIẾT ĐƯỢC CHO CẢ SQLite LẪN PostgreSQL. Chỗ này đã suýt gài một quả
# mìn: `DATETIME` là kiểu của SQLite/MySQL, PostgreSQL KHÔNG có kiểu tên như
# thế. Trên máy phát triển (SQLite) mọi thứ xanh; lên Render (PostgreSQL) thì
# `ALTER TABLE … ADD COLUMN verified_at DATETIME` vỡ, và vì cả vòng lặp nằm
# trong MỘT giao dịch nên app không khởi động nổi — hỏng ở đúng nơi không ai
# gỡ được. Dùng `TIMESTAMP`: chuẩn SQL, PostgreSQL hiểu, SQLite cũng nhận.
_ADDED_COLUMNS = [
    # Thẩm định hàng loạt chạy tiếp được sau khi máy chủ ngủ (2/10/2026). Bảng
    # đã chạy trên production với các lô đã xong → mặc định 'done'.
    ("batch_runs", "state", "VARCHAR(12) DEFAULT 'done'"),
    # Tiết lộ chọn lọc trên hồ sơ (3/10/2026) — bảng dossiers đã có dữ liệu thật.
    ("dossiers", "private_json", "TEXT"),
    ("api_keys", "calls_total", "INTEGER DEFAULT 0"),
    ("api_keys", "calls_period", "INTEGER DEFAULT 0"),
    ("api_keys", "period", "VARCHAR(7) DEFAULT ''"),
    ("api_keys", "plan", "VARCHAR(16) DEFAULT 'free'"),
    # Sổ điểm tự chấm — thêm vào bảng alerts đã có dữ liệu thật đang chạy.
    ("alerts", "outcome", "VARCHAR(16)"),
    ("alerts", "verified_at", "TIMESTAMP"),
    ("alerts", "verify_source", "VARCHAR(16) DEFAULT ''"),
    ("alerts", "verify_note", "TEXT DEFAULT ''"),
    ("alerts", "observed_peak", "FLOAT"),
    ("alerts", "window_days", "INTEGER DEFAULT 7"),
    ("alerts", "retro", "INTEGER DEFAULT 0"),
    # Đường một chạm.
    ("observations", "source", "VARCHAR(16) DEFAULT 'user'"),
    ("observations", "alert_id", "INTEGER"),
    # Đ11 — phân quyền cho database đã chạy trước khi có cột role.
    ("users", "role", "VARCHAR(16) DEFAULT 'user'"),
    # M4 — bản tin sáng.
    ("users", "morning_brief", "INTEGER DEFAULT 0"),
    ("users", "brief_last", "VARCHAR(10) DEFAULT ''"),
    # N1 — xác thực email.
    ("users", "email_verified", "INTEGER DEFAULT 0"),
    # N8 — đồng ý tách từng mục đích. Không cần grandfather đặc biệt: DEFAULT
    # của ALTER TABLE áp cho hàng cũ luôn đúng ý nghĩa muốn có (alerts/
    # observations giữ nguyên hành vi cũ = bật; research là tính năng MỚI nên
    # tắt cho tất cả, kể cả người dùng cũ, là đúng — trước đây chưa ai được hỏi).
    ("users", "consent_alerts", "INTEGER DEFAULT 1"),
    ("users", "consent_observations", "INTEGER DEFAULT 1"),
    ("users", "consent_research", "INTEGER DEFAULT 0"),
    # Đ11 — vai trò coop thật (trước chỉ là bình luận trong code, chưa ai dùng
    # được). Mặc định rỗng/tắt nên không tự lộ dữ liệu người dùng cũ cho ai cả.
    ("users", "coop_code", "VARCHAR(64) DEFAULT ''"),
    ("users", "share_with_coop", "INTEGER DEFAULT 0"),
    # "Rà soát ngay" chạy nền qua bảng jobs — tiến độ từng thửa.
    ("jobs", "progress_json", "TEXT"),
]


def _ensure_columns() -> None:
    """Thêm cột còn thiếu vào bảng đã tồn tại. Di trú nghèo nhưng đủ dùng.

    Có Alembic thì tốt hơn, nhưng nó thêm một bước triển khai nữa mà dự án ở
    quy mô này chưa cần. Khi schema bắt đầu đổi thường xuyên thì hãy chuyển.
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    have = set(insp.get_table_names())
    # MỖI CỘT MỘT GIAO DỊCH RIÊNG, và nuốt lỗi của từng cột.
    #
    # Trước đây cả vòng lặp nằm trong một `engine.begin()` không có try/except:
    # một kiểu dữ liệu sai ở cột thứ sáu làm hỏng luôn năm cột trước đó, ném
    # ngoại lệ ra khỏi init_db(), và MÁY CHỦ KHÔNG KHỞI ĐỘNG ĐƯỢC. Một bước di
    # trú phụ trợ không bao giờ được phép có quyền hạ cả hệ thống.
    #
    # Cột thêm hụt thì hỏng đúng tính năng dùng nó, và lỗi hiện trong log —
    # còn hơn nhiều so với một máy chủ chết im lặng lúc nửa đêm.
    for table, col, decl in _ADDED_COLUMNS:
        if table not in have:
            continue
        if col in {c["name"] for c in insp.get_columns(table)}:
            continue
        try:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {decl}"))
                # N1 — GRANDFATHER mọi tài khoản đã tồn tại TRƯỚC khi cột này
                # ra đời: họ chưa từng được yêu cầu xác thực, nên đột ngột cắt
                # cảnh báo của họ vì một yêu cầu MỚI thêm là một cách hỏng âm
                # thầm, khó chịu hơn hẳn không có tính năng này. Chỉ chạy ĐÚNG
                # MỘT LẦN — vòng lặp này bỏ qua cột đã tồn tại ở lần khởi động
                # sau, nên không backfill nhầm người đăng ký MỚI sau lần này.
                if table == "users" and col == "email_verified":
                    conn.execute(text("UPDATE users SET email_verified = 1"))
        except Exception as e:                       # noqa: BLE001
            print(f"[TerraTwin] Không thêm được cột {table}.{col} ({decl}): "
                  f"{type(e).__name__}: {e}")


def init_db() -> None:
    """Tạo bảng nếu chưa có, rồi bù cột còn thiếu cho database đã chạy."""
    Base.metadata.create_all(engine)
    _ensure_columns()


def get_session():
    """FastAPI dependency — mở/đóng session cho mỗi request."""
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()

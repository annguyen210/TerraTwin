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
    DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker,
)

DATABASE_URL = os.environ.get("TERRATWIN_DATABASE_URL", "sqlite:///./terratwin.db")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(120), default="")
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
    kind: Mapped[str] = mapped_column(String(16))       # webhook | email
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


Index("ix_alert_user_created", Alert.user_id, Alert.created_at.desc())


# Cột thêm sau khi đã có database chạy thật. `create_all` KHÔNG thêm cột vào
# bảng sẵn có, nên thiếu bước này thì bản deploy cũ sẽ đổ ngay lần truy vấn đầu
# — lỗi chỉ lộ ra ở production, không bao giờ lộ trong test trên database sạch.
_ADDED_COLUMNS = [
    ("api_keys", "calls_total", "INTEGER DEFAULT 0"),
    ("api_keys", "calls_period", "INTEGER DEFAULT 0"),
    ("api_keys", "period", "VARCHAR(7) DEFAULT ''"),
]


def _ensure_columns() -> None:
    """Thêm cột còn thiếu vào bảng đã tồn tại. Di trú nghèo nhưng đủ dùng.

    Có Alembic thì tốt hơn, nhưng nó thêm một bước triển khai nữa mà dự án ở
    quy mô này chưa cần. Khi schema bắt đầu đổi thường xuyên thì hãy chuyển.
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    have = set(insp.get_table_names())
    with engine.begin() as conn:
        for table, col, decl in _ADDED_COLUMNS:
            if table not in have:
                continue
            cols = {c["name"] for c in insp.get_columns(table)}
            if col in cols:
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {decl}"))


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

"""Twin engine (lõi dùng chung).

Phase 0: lưu Twin trong bộ nhớ. Khi triển khai thật, thay bằng PostGIS +
TimescaleDB và lưu các lớp dữ liệu (đất, cây trồng, độ ẩm, hạ tầng...).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.schemas import Location

_TWINS: dict[str, dict] = {}


def build_twin(location: Location) -> dict:
    twin_id = uuid.uuid4().hex[:12]
    twin = {
        "id": twin_id,
        "location": location.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _TWINS[twin_id] = twin
    return twin


def get_twin(twin_id: str) -> dict | None:
    return _TWINS.get(twin_id)

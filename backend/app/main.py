"""API TerraTwin (lõi).

Chạy: uvicorn app.main:app --port 8000
Cấu hình qua biến môi trường (xem .env.example):
  TERRATWIN_CORS        : danh sách origin cho CORS, phân tách bằng dấu phẩy (mặc định *)
  TERRATWIN_RATE_LIMIT  : số request/phút cho mỗi IP (mặc định 120; 0 = tắt)
  ANTHROPIC_API_KEY     : bật Copilot LLM thật (tùy chọn)
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.modules.registry import get_module, list_modules
from app.schemas import (
    Assessment, CopilotAnswer, Location, ModuleInfo, ScanResult,
    TerraScoreResult, WhatIfResult,
)
from app.services import (
    anomaly, backtest, copilot, explain, goalseek, hazard, scan, terrascore,
    timemachine, whatif,
)
from app.services.twin import build_twin

app = FastAPI(title="TerraTwin API", version="0.4.0")

_HAZARD_ONLY = f"Chỉ áp dụng cho module hiểm họa thời tiết: {', '.join(hazard.IDS)}"

_origins_env = os.environ.get("TERRATWIN_CORS", "*").strip()
_ORIGINS = ["*"] if _origins_env in ("", "*") else [o.strip() for o in _origins_env.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Rate limit đơn giản theo IP (sliding window, in-memory) ----
# Bảo vệ nguồn Open-Meteo/NASA free khỏi bị lạm dụng → chặn IP.
_RATE = int(os.environ.get("TERRATWIN_RATE_LIMIT", "120"))
_HITS: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if _RATE > 0 and request.url.path.startswith("/api/"):
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        dq = _HITS[ip]
        while dq and now - dq[0] > 60.0:
            dq.popleft()
        if len(dq) >= _RATE:
            return JSONResponse(
                status_code=429,
                content={"detail": f"Quá {_RATE} request/phút. Thử lại sau ít giây."},
            )
        dq.append(now)
    return await call_next(request)


class CopilotRequest(BaseModel):
    question: str
    location: Location


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "terratwin", "modules": len(list_modules())}


@app.get("/api/modules", response_model=list[ModuleInfo])
def modules() -> list[ModuleInfo]:
    return list_modules()


@app.post("/api/twin")
def create_twin(location: Location) -> dict:
    return build_twin(location)


@app.post("/api/assess/{module_id}", response_model=Assessment)
def assess(module_id: str, location: Location) -> Assessment:
    module = get_module(module_id)
    if module is None:
        raise HTTPException(status_code=404, detail=f"Không có mô-đun '{module_id}'")
    return module.assess(location)


@app.post("/api/terrascore", response_model=TerraScoreResult)
def terra(location: Location) -> TerraScoreResult:
    return terrascore.compute(location)


@app.post("/api/scan", response_model=ScanResult)
def scan_endpoint(location: Location) -> ScanResult:
    """Quét toàn cảnh thửa đất: cả 14 module + cảnh báo ưu tiên trong 1 lần gọi."""
    return scan.scan(location)


@app.post("/api/whatif/{module_id}", response_model=WhatIfResult)
def whatif_endpoint(module_id: str, location: Location) -> WhatIfResult:
    """Parallel Futures: mô phỏng nhiều kịch bản thời tiết cho 1 module hiểm họa."""
    result = whatif.run(module_id, location)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Module '{module_id}' chưa hỗ trợ what-if (chỉ: drought, flood, wildfire, landslide)",
        )
    return result


@app.post("/api/explain/{module_id}")
def explain_endpoint(module_id: str, location: Location) -> dict:
    """S07 Causal Explain — VÌ SAO chỉ số cao: phân rã đóng góp từng yếu tố
    bằng leave-one-out chính xác trên chính mô hình cảnh báo."""
    result = explain.explain(module_id, location.lat, location.lon)
    if result is None:
        raise HTTPException(status_code=404, detail=_HAZARD_ONLY)
    return result


@app.post("/api/goalseek/{module_id}")
def goalseek_endpoint(module_id: str, location: Location,
                      target: float | None = None) -> dict:
    """S03 Goal-Seek — mô phỏng ngược: cần điều kiện gì để an toàn, hoặc
    hiện còn chịu được bao nhiêu trước khi vượt ngưỡng."""
    result = goalseek.run(module_id, location.lat, location.lon, target)
    if result is None:
        raise HTTPException(status_code=404, detail=_HAZARD_ONLY)
    return result


@app.post("/api/timemachine/{module_id}")
def timemachine_endpoint(module_id: str, location: Location,
                         years: int = 10) -> dict:
    """S02 Counterfactual Time Machine — xác suất vượt ngưỡng suy từ analog
    ensemble: cùng cửa sổ lịch của N năm THẬT (ERA5) tại chính toạ độ này."""
    result = timemachine.run(module_id, location.lat, location.lon,
                             years=max(3, min(years, 30)))
    if result is None:
        raise HTTPException(status_code=404, detail=_HAZARD_ONLY)
    return result


@app.post("/api/anomaly")
def anomaly_endpoint(location: Location, years: int = 10) -> dict:
    """C10 Anomaly — tuần tới có bất thường so với khí hậu nền cùng kỳ không."""
    return anomaly.run(location.lat, location.lon, years=max(3, min(years, 30)))


@app.post("/api/copilot", response_model=CopilotAnswer)
def copilot_endpoint(req: CopilotRequest) -> CopilotAnswer:
    return copilot.answer(req.question, req.location)


@app.get("/api/backtest")
def backtest_list() -> list[dict]:
    """Danh sách sự kiện thiên tai lịch sử THẬT để kiểm chứng 'biết trước'."""
    return backtest.list_events()


@app.get("/api/backtest/{event_id}")
def backtest_run(event_id: str) -> dict:
    result = backtest.run_event(event_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Không có sự kiện '{event_id}'")
    return result

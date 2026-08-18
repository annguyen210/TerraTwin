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
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.db import init_db
from app.modules.registry import get_module, list_modules
from app.routes_account import router as account_router
from app.routes_data import router as data_router
from app.routes_learn import router as learn_router
from app.schemas import (
    Assessment, CopilotAnswer, Location, ModuleInfo, ScanResult,
    TerraScoreResult, WhatIfResult,
)
from app.services import (
    anomaly, backtest, copilot, explain, genome, goalseek, hazard, heatmap, llm,
    design, roadmap, scan, terrascore, timelapse, timemachine, whatif,
    whatif_nlp,
)
from app.services import twin as twin_service
from app import auth

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if not auth.SECRET_FROM_ENV:
        # Không hardcode secret. Cảnh báo rõ để production không quên đặt.
        print("[TerraTwin] CẢNH BÁO: chưa đặt TERRATWIN_SECRET — dùng secret ngẫu "
              "nhiên, mọi token sẽ mất hiệu lực khi restart. Đặt biến này trước "
              "khi triển khai thật.")
    yield


app = FastAPI(title="TerraTwin API", version="0.5.0", lifespan=lifespan)

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

# Sau reverse proxy (Render, nginx, Cloudflare), request.client.host là IP của
# PROXY — nghĩa là mọi người dùng dùng chung một hạn mức và app sập ngay khi có
# vài người vào cùng lúc. Đặt TERRATWIN_TRUST_PROXY=1 khi thực sự đứng sau proxy
# để đọc X-Forwarded-For. KHÔNG bật mặc định: nếu app phơi trực tiếp ra Internet,
# tin XFF cho phép client tự bịa IP và né hoàn toàn giới hạn.
_TRUST_PROXY = os.environ.get("TERRATWIN_TRUST_PROXY", "").strip() in ("1", "true", "yes")


def _client_ip(request: Request) -> str:
    if _TRUST_PROXY:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        real = request.headers.get("x-real-ip")
        if real:
            return real.strip()
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if _RATE > 0 and request.url.path.startswith("/api/"):
        ip = _client_ip(request)
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


app.include_router(account_router)
app.include_router(data_router)
app.include_router(learn_router)


class CopilotRequest(BaseModel):
    question: str
    location: Location


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "terratwin", "modules": len(list_modules())}


@app.get("/api/roadmap")
def roadmap_status() -> dict:
    """Trạng thái thật của 26 luồng tính năng — sinh từ mã nguồn, không viết tay."""
    return roadmap.status()


@app.get("/api/modules", response_model=list[ModuleInfo])
def modules() -> list[ModuleInfo]:
    return list_modules()


@app.post("/api/twin")
def build_twin_endpoint(location: Location) -> dict:
    """C01 Twin Builder — dựng bản sao số đầy đủ (không lưu).

    Muốn lưu lại thì đăng nhập và dùng POST /api/twins.
    """
    return twin_service.build(location)


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


@app.post("/api/heatmap/{module_id}")
def heatmap_endpoint(module_id: str, location: Location,
                     radius_km: float = 8.0, side: int = 7) -> dict:
    """C06 Risk Heatmap — lưới rủi ro quanh thửa đất, chạy đúng mô hình cảnh báo
    trên từng ô. Cả lưới chỉ tốn 1–2 lượt gọi nhờ truy vấn đa toạ độ."""
    result = heatmap.build(module_id, location.lat, location.lon,
                           radius_km=radius_km, side=side)
    if result is None:
        raise HTTPException(status_code=404, detail=_HAZARD_ONLY)
    return result


@app.post("/api/anomaly")
def anomaly_endpoint(location: Location, years: int = 10) -> dict:
    """C10 Anomaly — tuần tới có bất thường so với khí hậu nền cùng kỳ không."""
    return anomaly.run(location.lat, location.lon, years=max(3, min(years, 30)))


@app.post("/api/timelapse/{module_id}")
def timelapse_endpoint(module_id: str, location: Location,
                       years: int = 10) -> dict:
    """C04 Time-Lapse — rủi ro của thửa này đã đổi thế nào qua các năm.

    Đây là time-lapse của RỦI RO KHÍ HẬU từ ERA5, không phải phát hiện thay đổi
    bề mặt trên ảnh vệ tinh (cái đó cần Sentinel).
    """
    result = timelapse.build(module_id, location.lat, location.lon, years=years)
    if result is None:
        raise HTTPException(status_code=404, detail=_HAZARD_ONLY)
    return result


@app.post("/api/design")
def design_endpoint(location: Location) -> dict:
    """U03 Design Studio — sinh phương án canh tác cụ thể cho thửa đất."""
    return design.generate(location)


@app.post("/api/genome")
def genome_endpoint(location: Location, k: int = 5) -> dict:
    """S04 Twin Genome — tìm những vùng có 'bộ gen' đất đai giống thửa của bạn.

    Lần gọi đầu tiên phải dựng lưới tham chiếu toàn quốc (~1–2 phút); sau đó
    lấy từ cache 30 ngày. Gọi trước /api/genome/warm để dựng sẵn.
    """
    return genome.find_twins(location.lat, location.lon, k=k)


@app.post("/api/genome/warm")
def genome_warm(force: bool = False) -> dict:
    """Dựng sẵn lưới tham chiếu để lần hỏi đầu của người dùng không phải chờ."""
    ref = genome.build_reference(force=force)
    return {k: v for k, v in ref.items() if k != "cells"}


class AskRequest(BaseModel):
    question: str
    location: Location
    module_id: str = "flood"


@app.post("/api/ask")
def ask_endpoint(req: AskRequest) -> dict:
    """C03 What-If NLP — hỏi bằng lời, chạy mô phỏng thật.

    Câu hỏi chỉ dùng để CHỌN THAM SỐ; con số do mô hình vật lý tính.
    """
    return whatif_nlp.ask(req.question, req.location.lat, req.location.lon,
                          req.module_id)


@app.get("/api/llm")
def llm_status() -> dict:
    """Cấu hình LLM hiện tại (không bao giờ trả về khóa)."""
    return llm.info()


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

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
from app.routes_trust import router as trust_router
from app.schemas import (
    Assessment, CopilotAnswer, Location, ModuleInfo, ScanResult,
    TerraScoreResult, WhatIfResult,
)
from app.services import (
    advisor,
    anomaly, anomaly_ml, backtest, calibration, copilot, design, explain,
    future, genome, goalseek,
    hazard, heatmap, imagery, jobs, landcover, llm, mrv, place, region,
    passport, reqlang, roadmap, scan, sentinel,
    terrascore, timelapse, timemachine, whatif, whatif_nlp,
)
from app.services import twin as twin_service
from app import auth
from app.safelog import log


# Bộ hẹn giờ nền cho C05 Proactive Radar.
# 0 = tắt (dùng khi chạy nhiều worker hoặc đã có cron ngoài gọi /api/radar/run).
_RADAR_INTERVAL_H = float(os.environ.get("TERRATWIN_RADAR_INTERVAL_H", "6") or 0)

# Bộ hẹn giờ THỬ LẠI riêng cho các thửa bị 429 trong lần quét bỏ sót gần nhất
# (xem verify.retry_due_misses). Tách khỏi _RADAR_INTERVAL_H (mặc định 6 giờ)
# vì "thử lại sau 20-30 phút" cần một nhịp mịn hơn hẳn — nhưng rẻ: không làm
# gì cả (chỉ một lượt đọc kv_cache) trừ khi có thửa nào tới hạn thử lại.
_RADAR_RETRY_INTERVAL_MIN = float(os.environ.get("TERRATWIN_RADAR_RETRY_INTERVAL_MIN", "10") or 0)

# Hâm nóng cache ngay sau khi dựng lại tiến trình. "0" = tắt; mặc định bật.
_STARTUP_WARMUP = os.environ.get("TERRATWIN_STARTUP_WARMUP", "1").strip() != "0"


async def _radar_loop() -> None:
    """Quét định kỳ cho mọi người dùng.

    Chờ TRƯỚC rồi mới quét: khi Render/Fly khởi động lại container (chuyện xảy
    ra thường xuyên trên gói miễn phí) ta không muốn mỗi lần restart lại nã một
    loạt request vào Open-Meteo.

    KHÔNG đếm mù từ lúc tiến trình khởi động: một bộ đếm `sleep(interval)` đơn
    thuần bắt đầu lại từ 0 mỗi lần restart — nếu khoảng cách giữa hai lần
    restart luôn NGẮN HƠN interval (6 giờ, chuyện bình thường trên gói free)
    thì vòng lặp này KHÔNG BAO GIỜ quét được dù tiến trình luôn "đang chạy".
    Đo được đúng chuyện đó: /api/health.radar.last_sweep_at đứng yên ở null
    nhiều ngày liền. Sửa: đọc lần quét gần nhất đã LƯU BỀN (kv_cache, sống qua
    restart — xem radar.last_sweep) và chỉ còn chờ phần thời gian CÒN LẠI.
    """
    import asyncio
    from datetime import datetime, timezone

    from app.db import SessionLocal
    from app.services import radar as radar_svc

    interval = _RADAR_INTERVAL_H * 3600.0
    while True:
        try:
            def _remaining_wait() -> float:
                last = radar_svc.last_sweep()
                if not last or not last.get("at"):
                    return 0.0      # chưa từng quét lần nào trong đời database — quét ngay
                try:
                    last_dt = datetime.fromisoformat(last["at"])
                except ValueError:
                    return 0.0
                elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
                return max(0.0, interval - elapsed)

            wait = await asyncio.to_thread(_remaining_wait)
            if wait > 0:
                await asyncio.sleep(wait)
        except asyncio.CancelledError:
            return
        try:
            # Quét chạm mạng và database nên đẩy sang luồng phụ, không chặn
            # vòng lặp sự kiện đang phục vụ người dùng.
            def _sweep() -> dict:
                db = SessionLocal()
                try:
                    return radar_svc.sweep_all(db)
                finally:
                    db.close()

            r = await asyncio.to_thread(_sweep)
            if r["new_alerts"]:
                log(f"[TerraTwin] Rà soát nền: {r['users_scanned']} tài khoản · "
                      f"{r['plots_scanned']} thửa · {r['new_alerts']} cảnh báo mới "
                      f"· gửi {r['notifications_sent']} (lỗi {r['notifications_failed']}).")
        except asyncio.CancelledError:
            return
        except Exception as e:      # nền hỏng không được kéo sập API
            log(f"[TerraTwin] Rà soát nền lỗi: {type(e).__name__}: {e}")


async def _radar_retry_loop() -> None:
    """Thử lại các thửa bị bỏ qua vì 429 ở lượt quét bỏ sót gần nhất.

    Tách khỏi _radar_loop vì nhịp khác hẳn: _radar_loop chạy mỗi
    TERRATWIN_RADAR_INTERVAL_H (mặc định 6 giờ, khớp cron ngoài); vòng này
    chạy dày hơn (mặc định 10 phút) NHƯNG hầu như mỗi lần thức dậy đều không
    làm gì — verify.retry_due_misses() tự bỏ qua nếu hàng đợi rỗng hoặc chưa
    tới hạn (xem verify.RETRY_DELAY_MIN).
    """
    import asyncio

    from app.db import SessionLocal
    from app.services import verify as verify_svc

    interval = _RADAR_RETRY_INTERVAL_MIN * 60.0
    while True:
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return
        try:
            def _retry() -> dict:
                db = SessionLocal()
                try:
                    return verify_svc.retry_due_misses(db)
                finally:
                    db.close()

            r = await asyncio.to_thread(_retry)
            if r.get("retried"):
                log(f"[TerraTwin] Thử lại bỏ sót sau 429: {r['retried']} thửa · "
                      f"phục hồi {r.get('recovered', 0)} · vẫn hỏng "
                      f"{r.get('still_failed', 0)} · ghi thêm {r.get('misses_recorded', 0)} bỏ sót.")
        except asyncio.CancelledError:
            return
        except Exception as e:      # nền hỏng không được kéo sập API
            log(f"[TerraTwin] Thử lại bỏ sót lỗi: {type(e).__name__}: {e}")


async def _startup_warmup() -> None:
    """Nạp trước 8 địa điểm mẫu (app.warm.DEMO) NGAY sau khi dựng lại tiến
    trình — demo trước giám khảo không được rơi vào mô hình mẫu chỉ vì Render
    vừa restart mất cache.

    `app.warm` vốn là script CLI chạy TAY trước buổi thi (`python -m app.warm
    --demo`) — đúng nhưng không tự động: quên chạy tay một lần là mất tác
    dụng. Ở đây chạy CHÍNH warm_one() (tức chạy đúng lượt quét thật, không
    phải mẹo nạp riêng phần hiệu chuẩn — xem chú thích trong app/warm.py) một
    cách tự động mỗi khi tiến trình khởi động, giãn cách vài giây một điểm để
    không tự trói mình bằng chính lượt hâm nóng.
    """
    import asyncio

    from app.warm import DEMO, warm_one

    for lat, lon, name in DEMO:
        try:
            ok, total = await asyncio.to_thread(warm_one, lat, lon)
            if ok < total:
                log(f"[TerraTwin] Hâm nóng {name}: {ok}/{total} mô-đun có dữ liệu thật.")
        except asyncio.CancelledError:
            return
        except Exception as e:      # một điểm hỏng không được chặn các điểm sau
            log(f"[TerraTwin] Hâm nóng {name} lỗi: {type(e).__name__}: {e}")
        await asyncio.sleep(3.0)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    import asyncio

    init_db()
    if not auth.SECRET_FROM_ENV:
        # Không hardcode secret. Cảnh báo rõ để production không quên đặt.
        log("[TerraTwin] CẢNH BÁO: chưa đặt TERRATWIN_SECRET — dùng secret ngẫu "
              "nhiên, mọi token sẽ mất hiệu lực khi restart. Đặt biến này trước "
              "khi triển khai thật.")

    task = None
    if _RADAR_INTERVAL_H > 0:
        task = asyncio.create_task(_radar_loop())
        log(f"[TerraTwin] Rà soát chủ động: tự chạy mỗi {_RADAR_INTERVAL_H} giờ.")
    else:
        log("[TerraTwin] Rà soát chủ động: bộ hẹn giờ nội bộ TẮT — cảnh báo chỉ "
              "sinh khi có người gọi /api/radar/run.")

    retry_task = None
    if _RADAR_RETRY_INTERVAL_MIN > 0:
        retry_task = asyncio.create_task(_radar_retry_loop())

    warmup_task = None
    if _STARTUP_WARMUP:
        warmup_task = asyncio.create_task(_startup_warmup())
    try:
        yield
    finally:
        for t in (task, retry_task, warmup_task):
            if t is not None:
                t.cancel()
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass


app = FastAPI(title="TerraTwin API", version="0.5.0", lifespan=lifespan)

_HAZARD_ONLY = f"Chỉ áp dụng cho module hiểm họa thời tiết: {', '.join(hazard.IDS)}"

_origins_env = os.environ.get("TERRATWIN_CORS", "*").strip()
_ORIGINS = ["*"] if _origins_env in ("", "*") else [o.strip() for o in _origins_env.split(",")]

# Đ3 — quên một biến BẢO MẬT thì phải ỒN ÀO, không được im. CORS='*' ngoài môi
# trường dev nghĩa là mọi trang web đều gọi được API này. render.yaml có nhắc
# đặt TERRATWIN_CORS, nhưng nhắc thì quên được — nên chặn/kêu ngay lúc khởi động.
_IS_DEV = os.environ.get("TERRATWIN_ENV", "prod").strip().lower() == "dev"
if _ORIGINS == ["*"] and not _IS_DEV:
    if os.environ.get("TERRATWIN_STRICT", "").strip().lower() in ("1", "true", "yes"):
        raise RuntimeError(
            "TERRATWIN_CORS đang là '*' ngoài môi trường dev — TERRATWIN_STRICT=1 "
            "từ chối khởi động. Đặt TERRATWIN_CORS = đúng URL frontend.")
    log("[TerraTwin] CẢNH BÁO BẢO MẬT: TERRATWIN_CORS='*' — MỌI origin gọi được "
        "API. Đặt TERRATWIN_CORS = URL frontend trước khi mở cho người dùng thật "
        "(hoặc TERRATWIN_ENV=dev nếu đang chạy cục bộ).")

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
async def set_request_lang(request: Request, call_next):
    """Đặt ngôn ngữ request TRƯỚC KHI Pydantic validate body.

    VÌ SAO CẦN Ở ĐÂY, KHÔNG PHẢI TRONG ENDPOINT: mỗi endpoint tự gọi
    `reqlang.set_lang(lang)` bằng một dependency/tham số — nhưng Pydantic
    validate body (field_validator trên Location, ví dụ toạ độ ngoài khung
    Việt Nam) chạy TRƯỚC KHI vào tới thân hàm endpoint. Kết quả: lỗi 422 từ
    validator luôn tiếng Việt dù có ?lang=en, vì contextvar còn giữ giá trị
    mặc định lúc đó. Đặt ở middleware — chạy sớm hơn cả routing — để tránh.
    """
    reqlang.set_lang(request.query_params.get("lang"))
    return await call_next(request)


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
app.include_router(trust_router)


class CopilotRequest(BaseModel):
    question: str
    location: Location


@app.get("/api/health")
def health() -> dict:
    """Sức khoẻ máy chủ VÀ tình trạng hạn mức nguồn dữ liệu.

    Hạn mức nằm ở đây có chủ đích: Open-Meteo giới hạn theo NGÀY, và khi cạn thì
    mọi mô-đun đồng loạt trả "chưa đủ dữ liệu" — nhìn hệt như phần mềm hỏng.
    Người vận hành phải phân biệt được ngay "hết quota, mai lại chạy" với "code
    hỏng", nếu không sẽ đi sửa nhầm chỗ.
    """
    from app.services import notify, radar as radar_svc
    from app.services import realdata

    q = realdata.quota_status()
    last = radar_svc.last_sweep()

    # N1 — SMTP chưa cấu hình thì "quên mật khẩu" và "xác thực email" đều lặng
    # lẽ không hoạt động (đăng ký/forgot vẫn trả 200 để không lộ email nào tồn
    # tại — xem routes_account.py), nên phải BÁO RÕ ở đây, đặc biệt khi đang
    # chạy prod, để người vận hành biết mà không phải đoán qua một ticket
    # "sao tôi không nhận được email đặt lại mật khẩu".
    smtp_ok = notify.smtp_configured()
    is_prod = os.environ.get("TERRATWIN_ENV", "prod").strip().lower() != "dev"
    email = {
        "smtp_configured": smtp_ok,
        "forgot_password_works": smtp_ok,
        "email_verification_works": smtp_ok,
        "message": (
            None if smtp_ok else
            ("CẢNH BÁO: chưa đặt TERRATWIN_SMTP_* — \"quên mật khẩu\" và \"xác "
             "thực email\" KHÔNG hoạt động trên production. Người dùng bấm quên "
             "mật khẩu vẫn thấy thông báo đã gửi (cố ý, chống dò email) nhưng "
             "KHÔNG có gì tới hộp thư." if is_prod else
             "Chưa đặt TERRATWIN_SMTP_* — bình thường ở dev, trang /forgot trả "
             "kèm dev_link để thử không cần email thật.")),
    }

    return {"status": "degraded" if q["exhausted"] else "ok",
            "service": "terratwin", "modules": len(list_modules()),
            "quota": q, "jobs": jobs.stats(), "email": email,
            # Đếm lời gọi ra ngoài từ lúc tiến trình này khởi động + tỉ lệ
            # trúng cache — chẩn đoán "đang gọi thừa ở đâu" thay vì đoán. Có 6
            # nhóm URL Open-Meteo/MET Norway khác nhau; hit_rate_pct thấp là
            # dấu hiệu một mô-đun đang tự gọi riêng thay vì dùng chung cache.
            "calls": realdata.call_stats(),
            "radar": {
                "last_sweep_at": last.get("at") if last else None,
                "last_sweep": last,
            }}


@app.get("/api/roadmap")
def roadmap_status() -> dict:
    """Trạng thái thật của 26 luồng tính năng — sinh từ mã nguồn, không viết tay."""
    return roadmap.status()


@app.get("/api/modules", response_model=list[ModuleInfo])
def modules(lang: str = "vi") -> list[ModuleInfo]:
    reqlang.set_lang(lang)
    return list_modules()


@app.post("/api/twin")
def build_twin_endpoint(location: Location) -> dict:
    """C01 Twin Builder — dựng bản sao số đầy đủ (không lưu).

    Muốn lưu lại thì đăng nhập và dùng POST /api/twins.
    """
    return twin_service.build(location)


def _off_site_dict(lat: float, lon: float) -> dict | None:
    """Ngoài phạm vi phục vụ → dict giải thích; trong phạm vi → None.

    Bản dict này dành cho các endpoint KHÔNG trả về Assessment (đối chiếu
    ngưỡng, chấm bất thường). Trước đây tôi gọi thẳng _off_site() ở đó, nhưng
    hàm kia nhận (module, loc, reg) và trả Assessment — sai cả chữ ký lẫn kiểu
    trả về, và nó nổ 500 ngay lời gọi đầu tiên.

    Lỗi này lọt qua toàn bộ test vì test gọi hàm tính toán TRỰC TIẾP, không đi
    qua tầng HTTP. Đã bổ sung test gọi qua HTTP cho cả hai endpoint.
    """
    reg = region.classify(lat, lon)
    if reg.get("serviceable"):
        return None
    return {
        "available": False,
        "region": reg,
        "message": reg.get("note") or reqlang.tr("Ngoài phạm vi phục vụ.", "Out of service area."),
    }


def _off_site(module, loc: Location, reg: dict) -> Assessment:
    """Câu trả lời trung thực cho toạ độ ngoài phạm vi phục vụ.

    KHÔNG chạy mô-đun. Trước khi có hàm này, một điểm giữa Biển Đông nhận được
    "Điểm an toàn đất: 70/100" và "Thiếu nước NGHIÊM TRỌNG 96,7%" — con số đúng
    định dạng, sai hoàn toàn về ý nghĩa, và người dùng không có cách nào biết.
    """
    return Assessment(
        module_id=getattr(module, "id", "?"),
        module_name=module.disp_name() if hasattr(module, "disp_name") else getattr(module, "name", "?"),
        location=loc, status="out_of_scope", risk_level="unknown",
        is_real=False,
        headline=(reqlang.tr(
                      "Đây là mặt nước — TerraTwin phục vụ đất liền và đảo có dân cư",
                      "This is open water — TerraTwin serves mainland and inhabited islands")
                  if reg["kind"] == "sea" else
                  reqlang.tr(
                      f"Toạ độ ngoài phạm vi phục vụ ({(reg.get('country') or '?').upper()})",
                      f"Coordinate outside the service area ({(reg.get('country') or '?').upper()})")),
        detail=reg.get("note") or "",
        recommendation=(reqlang.tr("Bấm lại vào phần đất gần nhất.",
                                   "Click the nearest land instead.")
                        if reg["kind"] == "sea" else
                        reqlang.tr("TerraTwin hiệu chuẩn theo khí hậu và địa hình Việt Nam.",
                                   "TerraTwin is calibrated to Vietnam's climate and terrain.")),
        confidence=None,
        data_sources=[reqlang.tr("Cao độ DEM (Open-Meteo)", "DEM elevation (Open-Meteo)")]
        + (["Nominatim / OpenStreetMap"] if reg.get("country") else []),
    )


@app.post("/api/assess/{module_id}", response_model=Assessment)
def assess(module_id: str, location: Location, lang: str = "vi") -> Assessment:
    reqlang.set_lang(lang)
    module = get_module(module_id)
    if module is None:
        raise HTTPException(status_code=404, detail=f"Không có mô-đun '{module_id}'")
    reg = region.classify(location.lat, location.lon)
    if not reg["serviceable"]:
        return _off_site(module, location, reg)
    return module.assess(location)


@app.post("/api/terrascore", response_model=TerraScoreResult)
def terra(location: Location, lang: str = "vi") -> TerraScoreResult:
    reqlang.set_lang(lang)
    reg = region.classify(location.lat, location.lon)
    if not reg["serviceable"]:
        return TerraScoreResult(
            location=location, score=0, grade="—",
            summary=reg.get("note") or reqlang.tr("Ngoài phạm vi phục vụ.", "Out of service area."),
            real_data_ratio=0.0, region=reg)
    r = terrascore.compute(location)
    r.region = reg
    return r


@app.post("/api/scan", response_model=ScanResult)
def scan_endpoint(location: Location, deep: bool = False, lang: str = "vi") -> ScanResult:
    """Quét toàn cảnh thửa đất: mọi mũi nhọn nhẹ + cảnh báo ưu tiên, một lần gọi.

    Chặn trước ở đây thay vì để từng mô-đun tự xoay xở: mặt biển và đất nước
    khác không phải chuyện của mười sáu mô-đun, mà là chuyện của toạ độ.
    """
    reqlang.set_lang(lang)
    reg = region.classify(location.lat, location.lon)
    if not reg["serviceable"]:
        from datetime import datetime, timezone
        return ScanResult(
            location=location,
            terrascore=TerraScoreResult(
                location=location, score=0, grade="—",
                summary=reg.get("note") or reqlang.tr("Ngoài phạm vi phục vụ.", "Out of service area."),
                real_data_ratio=0.0),
            modules=[], alerts=[], real_data_ratio=0.0, region=reg,
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))

    # deep=true chạy cả những mũi nhọn NẶNG (cần ảnh vệ tinh, 6–60 giây mỗi
    # cái). Giao diện gọi lượt nhanh trước để có câu trả lời trong vài giây,
    # rồi gọi lượt sâu ở nền và điền dần — thay vì để bảy ô treo ở "đang kiểm
    # tra" mãi mãi, thứ trông y hệt như thiếu dữ liệu.
    r = scan.scan(location, include_heavy=deep)
    r.region = reg
    return r


@app.post("/api/plan")
def plan_endpoint(location: Location, crop: str = "lua", lang: str = "vi") -> dict:
    """KẾ HOẠCH THỬA CỦA BẠN — gom cảnh báo thành việc-cần-làm-có-ngày, ngày an
    toàn, giá trị chịu rủi ro (ước lượng thô, khai báo rõ), và trạng thái tự canh.

    Cùng cửa chặn như /api/scan: mặt biển / nước khác không có kế hoạch mùa vụ.
    """
    reqlang.set_lang(lang)
    reg = region.classify(location.lat, location.lon)
    if not reg["serviceable"]:
        return {"serviceable": False, "region": reg,
                "message": reg.get("note") or reqlang.tr("Ngoài phạm vi phục vụ.", "Out of service area.")}
    out = advisor.build(location, crop=crop)
    out["region"] = reg
    out["serviceable"] = True
    return out


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
def explain_endpoint(module_id: str, location: Location, lang: str = "vi") -> dict:
    """S07 Causal Explain — VÌ SAO chỉ số cao: phân rã đóng góp từng yếu tố
    bằng leave-one-out chính xác trên chính mô hình cảnh báo."""
    reqlang.set_lang(lang)
    result = explain.explain(module_id, location.lat, location.lon)
    if result is None:
        raise HTTPException(status_code=404, detail=_HAZARD_ONLY)
    return result


@app.post("/api/goalseek/{module_id}")
def goalseek_endpoint(module_id: str, location: Location,
                      target: float | None = None, lang: str = "vi") -> dict:
    """S03 Goal-Seek — mô phỏng ngược: cần điều kiện gì để an toàn, hoặc
    hiện còn chịu được bao nhiêu trước khi vượt ngưỡng."""
    reqlang.set_lang(lang)
    result = goalseek.run(module_id, location.lat, location.lon, target)
    if result is None:
        raise HTTPException(status_code=404, detail=_HAZARD_ONLY)
    return result


@app.post("/api/timemachine/{module_id}")
def timemachine_endpoint(module_id: str, location: Location,
                         years: int = 10, lang: str = "vi") -> dict:
    """S02 Counterfactual Time Machine — xác suất vượt ngưỡng suy từ analog
    ensemble: cùng cửa sổ lịch của N năm THẬT (ERA5) tại chính toạ độ này."""
    reqlang.set_lang(lang)
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


@app.post("/api/heatmap/{module_id}/timeline")
def heatmap_timeline(module_id: str, location: Location,
                     radius_km: float = 8.0, side: int = 7) -> dict:
    """C02 + C06 — diễn tiến rủi ro theo NGÀY trên lưới, cả 4 kịch bản.

    Tốn đúng bằng một lượt bản đồ nhiệt: dữ liệu 7 ngày vốn đã được tải cho mọi
    ô rồi bị bỏ đi chỉ giữ đỉnh. Trả đủ để giao diện phát lại tại chỗ, không
    gọi mạng thêm lần nào khi người dùng kéo trượt ngày hay đổi kịch bản.
    """
    reg = region.classify(location.lat, location.lon)
    if not reg["serviceable"]:
        return {"available": False, "region": reg,
                "message": reg.get("note") or "Ngoài phạm vi phục vụ."}
    r = heatmap.timeline(module_id, location.lat, location.lon,
                         radius_km=radius_km, side=side)
    if r is None:
        raise HTTPException(status_code=404, detail=_HAZARD_ONLY)
    r["available"] = True
    return r


@app.post("/api/probability/{module_id}")
def probability_endpoint(module_id: str, location: Location) -> dict:
    """A3 — XÁC SUẤT vượt ngưỡng trong 7 ngày tới, từ tổ hợp dự báo vật lý.

    Chạy đúng chỉ số hiểm hoạ trên từng thành viên rồi đếm phân vị — xác suất
    THẬT, không bịa từ một con số điểm. Trả P10/P50/P90 + % khả năng vượt ngưỡng.
    """
    from app.services import probabilistic

    off = _off_site_dict(location.lat, location.lon)
    if off:
        return off
    return probabilistic.forecast(module_id, location.lat, location.lon)


@app.post("/api/anomaly")
def anomaly_endpoint(location: Location, years: int = 10, lang: str = "vi") -> dict:
    """C10 Anomaly — tuần tới có bất thường so với khí hậu nền cùng kỳ không."""
    reqlang.set_lang(lang)
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


class ContrastRequest(BaseModel):
    location: Location


@app.post("/api/contrast")
def contrast_endpoint(req: ContrastRequest, lang: str = "vi") -> dict:
    """Đối chứng: ngưỡng chung cả nước vs hiệu chuẩn theo chính thửa này.

    LÝ DO TỒN TẠI. Điểm mạnh nhất của sản phẩm là thứ không nhìn thấy được:
    những lần báo động giả ĐÃ KHÔNG xảy ra. Người dùng mở app chỉ thấy "hôm nay
    an toàn" — y hệt mọi phần mềm khác, nên không có cơ sở nào để tin cái này
    hơn cái kia. Endpoint này biến cái vô hình thành con số tại chính toạ độ họ
    vừa bấm.

    Không tốn thêm lượt gọi mạng: dùng lại phân bố 10 năm mà bước hiệu chuẩn
    trong lượt quét vừa rồi đã tải và cache.
    """
    reqlang.set_lang(lang)
    off = _off_site_dict(req.location.lat, req.location.lon)
    if off:
        return off
    out = []
    for mid in ("flood", "landslide", "drought", "wildfire"):
        c = calibration.contrast(mid, req.location.lat, req.location.lon)
        if c:
            out.append(c)
    if not out:
        return {"available": False,
                "message": reqlang.tr("Chưa tải được lịch sử 10 năm cho điểm này.",
                                      "Couldn't load the 10-year history for this point.")}
    return {"available": True, "modules": out}


class ImageryRequest(BaseModel):
    location: Location
    buffer_m: float = 1200.0


@app.post("/api/imagery")
def imagery_endpoint(req: ImageryRequest, lang: str = "vi") -> dict:
    """Ảnh vệ tinh THẬT của thửa đất — màu thật, sức sống cây, và đối chiếu năm ngoái.

    Thứ TerraTwin thiếu suốt từ đầu: người dùng chưa bao giờ NHÌN THẤY mảnh đất
    của mình, chỉ đọc câu văn kể về nó. Chữ "Twin" hứa một bản sao của vật thật.

    Trả về ĐƯỜNG DẪN ảnh chứ không tải ảnh qua đây — mỗi tấm nửa megabyte, đẩy
    qua máy chủ gói free là tự bóp cổ mình mà chẳng lợi gì, vì nguồn vốn công khai.
    """
    reqlang.set_lang(lang)
    off = _off_site_dict(req.location.lat, req.location.lon)
    if off:
        return off
    return imagery.plot_view(req.location.lat, req.location.lon,
                             buffer_m=max(150.0, min(req.buffer_m, 3000.0)))


@app.post("/api/future/{module_id}")
def future_endpoint(module_id: str, location: Location) -> dict:
    """S10 ③ — Ảnh 'tương lai': ảnh vệ tinh THẬT + lớp phủ DỰ PHÓNG theo kịch bản.

    Nền là ảnh thật có ngày chụp; lớp phủ là mô phỏng kịch bản (đã hiệu chuẩn +
    backtest), vẽ tách khỏi ảnh và ghi rõ 'dự phóng' — không có điểm ảnh nào do
    model tưởng tượng.
    """
    off = _off_site_dict(location.lat, location.lon)
    if off:
        return off
    return future.build(module_id, location.lat, location.lon)


@app.post("/api/passport")
def passport_endpoint(req: ContrastRequest, lang: str = "vi") -> dict:
    """Hồ sơ riêng của một thửa: địa hình tương đối + mười năm hiểm hoạ.

    Đây là câu trả lời cho "phần mềm này hơn app thời tiết ở chỗ nào". App thời
    tiết biết trời sắp mưa bao nhiêu; nó không biết thửa của bạn nằm cao hay
    trũng so với đất xung quanh, và không biết mười năm qua đã có bao nhiêu lần
    nước lên tới đây.
    """
    reqlang.set_lang(lang)
    off = _off_site_dict(req.location.lat, req.location.lon)
    if off:
        return off
    return passport.build(req.location.lat, req.location.lon)


@app.get("/api/landcover")
def landcover_status() -> dict:
    """Trạng thái mô hình học sâu phân đoạn lớp phủ.

    Nói rõ đang thiếu gì và các lệnh để tự chạy — vì việc còn lại nằm ở máy có
    GPU, không nằm trong tay máy chủ này.
    """
    return landcover.status()


@app.get("/api/place")
def place_search(q: str = "") -> dict:
    """Tìm xã/huyện/tỉnh theo tên → toạ độ.

    Có endpoint này thì màn hình đầu mới hỏi được "ruộng của bạn ở đâu" bằng
    tiếng Việt, thay vì bắt người dùng tự mò trên bản đồ cả nước.
    """
    return place.search(q)


@app.get("/api/model")
def model_card() -> dict:
    """Thẻ mô hình đã huấn luyện — công bố cả chỗ nó KHÔNG thắng.

    Bảng `comparison` giữ nguyên mọi mức báo động đã thử, kể cả mức mô hình chỉ
    hoà với cách cũ. Đưa ra hết là cách duy nhất để người đọc tự kiểm tra thay
    vì phải tin.
    """
    return anomaly_ml.model_card()


class AnomalyMlRequest(BaseModel):
    location: Location


@app.post("/api/anomaly-ml")
def anomaly_ml_endpoint(req: AnomalyMlRequest, lang: str = "vi") -> dict:
    """Chấm độ hiếm của TỔ HỢP điều kiện hôm nay, bằng mô hình đã huấn luyện.

    Đây là chỉ số ĐỐI CHIẾU. Nó không được phép nâng hay hạ mức rủi ro của
    module nào — vì trên 5 năm kiểm tra nó chỉ hoà với cách xét từng biến ở mức
    vận hành 2%.
    """
    reqlang.set_lang(lang)
    off = _off_site_dict(req.location.lat, req.location.lon)
    if off:
        return off
    r = anomaly_ml.score(req.location.lat, req.location.lon)
    if r is None:
        return {"available": False,
                "message": reqlang.tr(
                    "Chưa có mô hình hoặc không đủ dữ liệu lịch sử cho "
                    "điểm này. Huấn luyện: python -m app.ml.train",
                    "No trained model or not enough historical data for this "
                    "point yet. Train with: python -m app.ml.train")}
    return r


@app.get("/api/satellite")
def satellite_status() -> dict:
    """Ảnh vệ tinh đã nối chưa — và nếu chưa thì thiếu chính xác thứ gì."""
    s = sentinel.status()
    s["unlocks"] = ["pest", "yield", "carbon", "storm_damage", "illegal_build"]
    return s


class MrvRequest(BaseModel):
    location: Location
    project_name: str = ""
    # Hệ số sinh khối địa phương (tấn chất khô/ha) từ khảo sát ô mẫu. Có thì báo
    # cáo lên Tier 2; không có thì dùng mặc định IPCC Tier 1.
    agb_t_ha: float | None = None


@app.post("/api/mrv")
def mrv_endpoint(req: MrvRequest, lang: str = "vi") -> dict:
    """C07 — Báo cáo MRV carbon/ESG, có mã băm chống sửa."""
    reqlang.set_lang(lang)
    return mrv.build(req.location.lat, req.location.lon,
                     agb_t_ha=req.agb_t_ha, project_name=req.project_name)


class ProvenanceRequest(BaseModel):
    location: Location
    start: str
    end: str
    product: str = ""
    grower: str = ""


@app.post("/api/provenance")
def provenance_endpoint(req: ProvenanceRequest) -> dict:
    """SUP-12 — hồ sơ truy xuất: điều kiện môi trường THẬT suốt vụ, có mã băm."""
    from app.modules.group_d import provenance

    return provenance(req.location, req.start, req.end,
                      product=req.product, grower=req.grower)


@app.post("/api/mrv/verify")
def mrv_verify(report: dict) -> dict:
    """Kiểm tra một báo cáo MRV còn nguyên vẹn hay đã bị sửa sau khi lập."""
    return mrv.verify(report)


@app.post("/api/change-detect")
def change_detect_endpoint(location: Location, months: int = 24) -> dict:
    """A7 — phát hiện mất tán cây bền vững trên chuỗi NDVI 24 tháng
    (BFAST/CUSUM rút gọn) — phân biệt được với dao động mùa vụ (vd lúa ba vụ),
    khác mrv.build() vốn chỉ so hai lát cắt (năm nay vs năm ngoái)."""
    from app.services import change_detect

    return change_detect.detect(location.lat, location.lon, months=max(6, min(months, 36)))


@app.post("/api/auto-boundary")
def auto_boundary_endpoint(location: Location, buffer_m: float = 500.0) -> dict:
    """A8 — tự vẽ ranh thửa bằng watershed trên độ dốc NDVI quanh điểm bấm
    (khung ~1km, ảnh Sentinel-2 gần nhất qua Planetary Computer)."""
    from app.services import watershed

    return watershed.extract_boundary(location.lat, location.lon,
                                      buffer_m=max(100.0, min(buffer_m, 1500.0)))


@app.post("/api/report/sign")
def report_sign(facts: dict) -> dict:
    """A9/G1 — ký tờ trình rủi ro (băm SHA-256 + dấu thời gian) để ngân hàng /
    bảo hiểm / người mua tự kiểm bản in không bị sửa."""
    from app.services import report

    return report.sign(facts)


@app.post("/api/report/verify")
def report_verify(signed: dict) -> dict:
    """Kiểm một tờ trình đã ký còn nguyên vẹn hay đã bị sửa sau khi lập."""
    from app.services import report

    return report.verify(signed)


@app.post("/api/genome")
def genome_endpoint(location: Location, k: int = 5, lang: str = "vi") -> dict:
    """S04 Twin Genome — tìm những vùng có 'bộ gen' đất đai giống thửa của bạn.

    Lần gọi đầu tiên phải dựng lưới tham chiếu toàn quốc (~1–2 phút); sau đó
    lấy từ cache 30 ngày. Gọi trước /api/genome/warm để dựng sẵn.
    """
    reqlang.set_lang(lang)
    return genome.find_twins(location.lat, location.lon, k=k)


@app.post("/api/genome/warm")
def genome_warm(force: bool = False, background: bool = True) -> dict:
    """Dựng sẵn lưới tham chiếu để lần hỏi đầu của người dùng không phải chờ.

    Mặc định chạy NỀN và trả ngay mã việc. Dựng lưới mất 1–2 phút, mà Render và
    phần lớn proxy cắt kết nối trước đó — người dùng thấy lỗi trong khi máy chủ
    vẫn đang chạy đúng. Đặt background=false nếu muốn chờ tại chỗ (dùng cho
    script triển khai, không dùng cho trình duyệt).
    """
    if not background:
        ref = genome.build_reference(force=force)
        return {k: v for k, v in ref.items() if k != "cells"}

    def _work():
        ref = genome.build_reference(force=force)
        return {k: v for k, v in ref.items() if k != "cells"}

    job_id = jobs.submit("genome_warm", _work, "Dựng lưới bộ gen toàn quốc")
    return {"job_id": job_id, "state": "queued",
            "poll": f"/api/jobs/{job_id}",
            "message": ("Đang dựng lưới ở chế độ nền (1–2 phút). Hỏi lại "
                        "/api/jobs/{id} để lấy kết quả.")}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    """Trạng thái một việc chạy nền."""
    st = jobs.status(job_id)
    if st is None:
        raise HTTPException(
            status_code=404,
            detail=("Không có việc nào mang mã này. Hàng đợi nằm trong bộ nhớ "
                    "nên khởi động lại máy chủ là mất; kết quả cũng chỉ giữ 30 phút."))
    return st


@app.get("/api/jobs")
def jobs_overview() -> dict:
    """Sức khoẻ hàng đợi và trần gọi ra ngoài."""
    return jobs.stats()


class AskRequest(BaseModel):
    question: str
    location: Location
    module_id: str = "flood"


@app.post("/api/ask")
def ask_endpoint(req: AskRequest, lang: str = "vi") -> dict:
    """C03 What-If NLP — hỏi bằng lời, chạy mô phỏng thật.

    Câu hỏi chỉ dùng để CHỌN THAM SỐ; con số do mô hình vật lý tính.
    """
    reqlang.set_lang(lang)
    return whatif_nlp.ask(req.question, req.location.lat, req.location.lon,
                          req.module_id)


@app.get("/api/llm")
def llm_status() -> dict:
    """Cấu hình LLM hiện tại (không bao giờ trả về khóa)."""
    return llm.info()


@app.get("/api/guard/stats")
def guard_stats() -> dict:
    """A2 — rào chắn con số đã chặn bao nhiêu lần LLM bịa số.

    Công khai và công bố như sổ điểm: cơ chế chống bịa số CÓ chạy hay không thì
    đo được, không phải một dòng hứa trong prompt.
    """
    from app.services import guard

    return guard.stats()


@app.post("/api/copilot", response_model=CopilotAnswer)
def copilot_endpoint(req: CopilotRequest, lang: str = "vi") -> CopilotAnswer:
    reqlang.set_lang(lang)
    return copilot.answer(req.question, req.location)


@app.get("/api/backtest")
def backtest_list(lang: str = "vi") -> list[dict]:
    """Danh sách sự kiện thiên tai lịch sử THẬT để kiểm chứng 'biết trước'."""
    reqlang.set_lang(lang)
    return backtest.list_events()


@app.get("/api/backtest/{event_id}")
def backtest_run(event_id: str, lang: str = "vi") -> dict:
    reqlang.set_lang(lang)
    result = backtest.run_event(event_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Không có sự kiện '{event_id}'")
    return result

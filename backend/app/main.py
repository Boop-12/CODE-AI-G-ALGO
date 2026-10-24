import logging
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.api.routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("gnkalgo")
app = FastAPI(title=settings.PROJECT_NAME, openapi_url="/api/openapi.json", docs_url="/api/docs", redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=True, allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type", "Idempotency-Key"])

@app.middleware("http")
async def request_security(request: Request, call_next):
    started = time.monotonic()
    origin = request.headers.get("origin")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if (origin and origin not in settings.origins) or (request.cookies.get("gnk_session") and not origin):
            return JSONResponse({"detail": "Origin check failed"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    logger.info("method=%s path=%s status=%s duration_ms=%.1f", request.method, request.url.path, response.status_code, (time.monotonic() - started) * 1000)
    return response

@app.get("/api/health")
async def health():
    return {"status": "ok", "mode": "paper", "live_trading": False}

@app.get("/api/ready")
async def ready():
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1 FROM paper_account LIMIT 1"))
        return {"status": "ready"}
    except Exception:
        return JSONResponse({"status": "unavailable"}, status_code=503)

app.include_router(router, prefix="/api/v1")

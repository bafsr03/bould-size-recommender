import os
import time
import hashlib
from typing import Any, Dict
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import structlog

from .config import settings
from .routers.recommend import router as recommend_router
from .routers.tryon import router as tryon_router
from .security import create_jwt


logger = structlog.get_logger("bould")


app = FastAPI(title="Bould Size Recommender", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Simple in-memory cache and token-bucket rate limit
_cache: Dict[str, Dict[str, Any]] = {}
_cache_exp: Dict[str, float] = {}
_buckets: Dict[str, tuple[float, float]] = {}


def _cache_get(key: str):
    now = time.time()
    if key in _cache and _cache_exp.get(key, 0) > now:
        return _cache[key]
    if key in _cache:
        _cache.pop(key, None)
        _cache_exp.pop(key, None)
    return None


def _cache_set(key: str, value: Dict[str, Any], ttl: int):
    _cache[key] = value
    _cache_exp[key] = time.time() + ttl


def _rate_limit(ident: str, requests_per_min: int, burst: int) -> None:
    refill_rate = requests_per_min / 60.0
    capacity = float(burst)
    now = time.time()
    tokens, last = _buckets.get(ident, (capacity, now))
    tokens = min(capacity, tokens + refill_rate * (now - last))
    if tokens < 1.0:
        raise JSONResponse(status_code=429, content={"detail": "Too Many Requests"})
    _buckets[ident] = (tokens - 1.0, now)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    resp = None
    try:
        # rate limit per client ip
        client_ip = request.client.host if request.client else "unknown"
        try:
            _rate_limit(client_ip, settings.rate_limit_per_min, settings.rate_limit_burst)
        except JSONResponse as rl:
            return rl
        resp = await call_next(request)
        return resp
    finally:
        duration_ms = int((time.time() - start) * 1000)
        logger.info("request", path=str(request.url.path), method=request.method, status=getattr(resp, "status_code", 0), duration_ms=duration_ms)


@app.exception_handler(Exception)
async def handle_exceptions(request: Request, exc: Exception):
    logger.error("error", path=str(request.url.path), error=str(exc))
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/v1/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/auth/token")
async def issue_token():
    token = create_jwt("shopify-backend")
    return {"token": token}


# Ensure storage dir
os.makedirs(settings.storage_dir, exist_ok=True)
app.mount("/files", StaticFiles(directory=settings.storage_dir), name="files")

# Routers under versioned prefix
app.include_router(recommend_router, prefix="/v1")
app.include_router(tryon_router, prefix="/v1")

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
from .routers.process import router as process_router
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
def _validate_config() -> None:
    strict = os.getenv("STRICT_CONFIG", "0") == "1"
    errors = []
    if not settings.api_key or settings.api_key == "change-me":
        errors.append("API_KEY must be set to a secure value")
    if not settings.garments_api_base:
        errors.append("GARMENTS_API_BASE must be set")
    if not settings.body_api_base:
        errors.append("BODY_API_BASE must be set")
    if (settings.vto_provider or "mock").lower() == "nano":
        if not settings.public_base_url:
            errors.append("PUBLIC_BASE_URL must be set for nano provider")
        if not settings.nano_api_key:
            errors.append("NANO_API_KEY must be set for nano provider")
    if errors:
        if strict:
            raise RuntimeError("Configuration error: " + "; ".join(errors))
        else:
            for e in errors:
                logger.warning("config_warning", warning=e)



@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    request_id = hashlib.md5(f"{request.client.host if request.client else 'unknown'}{time.time()}".encode()).hexdigest()[:8]
    resp = None
    
    try:
        # rate limit per client ip
        client_ip = request.client.host if request.client else "unknown"
        try:
            _rate_limit(client_ip, settings.rate_limit_per_min, settings.rate_limit_burst)
        except JSONResponse as rl:
            logger.warning("rate_limit_exceeded", client_ip=client_ip, request_id=request_id)
            return rl
            
        # Log request details
        logger.info("request_started", 
                   request_id=request_id,
                   path=str(request.url.path), 
                   method=request.method,
                   client_ip=client_ip,
                   user_agent=request.headers.get("user-agent", "unknown"),
                   content_type=request.headers.get("content-type", "unknown"))
        
        resp = await call_next(request)
        return resp
        
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        logger.error("request_failed", 
                    request_id=request_id,
                    path=str(request.url.path), 
                    method=request.method,
                    error=str(e),
                    duration_ms=duration_ms,
                    exc_info=True)
        raise
    finally:
        duration_ms = int((time.time() - start) * 1000)
        status_code = getattr(resp, "status_code", 0) if resp else 0
        logger.info("request_completed", 
                   request_id=request_id,
                   path=str(request.url.path), 
                   method=request.method, 
                   status=status_code, 
                   duration_ms=duration_ms)


@app.exception_handler(Exception)
async def handle_exceptions(request: Request, exc: Exception):
    request_id = hashlib.md5(f"{request.client.host if request.client else 'unknown'}{time.time()}".encode()).hexdigest()[:8]
    
    # Enhanced error logging
    logger.error("unhandled_exception", 
                request_id=request_id,
                path=str(request.url.path), 
                method=request.method,
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True)
    
    return JSONResponse(
        status_code=500, 
        content={
            "detail": "Internal server error",
            "error_code": "INTERNAL_ERROR",
            "request_id": request_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
    )


@app.get("/v1/health")
async def health():
    return {"status": "ok"}


@app.get("/v1/debug/status")
async def debug_status():
    """Debug endpoint to check API health and system status"""
    try:
        # Check if storage directory exists and is writable
        storage_status = "ok"
        try:
            os.makedirs(settings.storage_dir, exist_ok=True)
            test_file = os.path.join(settings.storage_dir, "test_write.tmp")
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
        except Exception as e:
            storage_status = f"error: {str(e)}"
        
        # Check cache status
        cache_entries = len(_cache)
        cache_expired = len([k for k, v in _cache_exp.items() if v < time.time()])
        
        return {
            "status": "ok",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "storage": {
                "directory": settings.storage_dir,
                "status": storage_status
            },
            "cache": {
                "entries": cache_entries,
                "expired": cache_expired
            },
            "rate_limiting": {
                "requests_per_min": settings.rate_limit_per_min,
                "burst_capacity": settings.rate_limit_burst,
                "active_buckets": len(_buckets)
            }
        }
    except Exception as e:
        logger.error("debug_status_error", error=str(e), exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "error": str(e),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
        )


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
app.include_router(process_router, prefix="/v1")

# Validate configuration at import time (warnings by default; set STRICT_CONFIG=1 to enforce)
_validate_config()

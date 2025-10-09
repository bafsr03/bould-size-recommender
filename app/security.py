from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from fastapi import Depends, Header, HTTPException, status
from .config import settings


async def verify_api_key(authorization: str | None = Header(None), x_api_key: str | None = Header(None)) -> None:
    provided = None
    if x_api_key:
        provided = x_api_key
    elif authorization and authorization.lower().startswith("bearer "):
        provided = authorization.split(" ", 1)[1]
    if not provided or provided != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def create_jwt(sub: str, ttl_seconds: int | None = None, aud: Optional[str] = None, iss: Optional[str] = None) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": sub,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds or settings.jwt_ttl_seconds)).timestamp()),
    }
    if aud:
        payload["aud"] = aud
    if iss:
        payload["iss"] = iss
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def verify_jwt(token: str) -> dict:
    try:
        options = {"verify_aud": bool(settings.jwt_audience)}
        decoded = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience=settings.jwt_audience if settings.jwt_audience else None,
            issuer=settings.jwt_issuer if settings.jwt_issuer else None,
            options=options,
        )
        return decoded
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

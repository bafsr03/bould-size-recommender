import os
from pydantic import BaseModel


class Settings(BaseModel):
    api_key: str = os.getenv("API_KEY", "change-me")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")

    garments_api_base: str = os.getenv("GARMENTS_API_BASE", "http://localhost:8001/v1")
    body_api_base: str = os.getenv("BODY_API_BASE", "http://localhost:8002/api/v1")

    body_api_username: str = os.getenv("BODY_API_USERNAME", "testuser")
    body_api_password: str = os.getenv("BODY_API_PASSWORD", "testpassword")

    recommender_unit: str = os.getenv("RECOMMENDER_UNIT", "cm")

    vto_provider: str = os.getenv("VTO_PROVIDER", "mock")

    storage_dir: str = os.getenv("STORAGE_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage")))

    # JWT
    jwt_secret: str = os.getenv("JWT_SECRET", "dev-secret")
    jwt_audience: str | None = os.getenv("JWT_AUDIENCE")
    jwt_issuer: str | None = os.getenv("JWT_ISSUER")
    jwt_ttl_seconds: int = int(os.getenv("JWT_TTL_SECONDS", "3600"))

    # Rate limit (token bucket)
    rate_limit_per_min: int = int(os.getenv("RATE_LIMIT_PER_MIN", "60"))
    rate_limit_burst: int = int(os.getenv("RATE_LIMIT_BURST", "30"))

    # Cache TTL seconds
    cache_ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", "600"))

    # Nanobanana (KIE AI) API
    nano_api_base: str = os.getenv("NANO_API_BASE", "https://api.kie.ai")
    nano_api_key: str | None = os.getenv("NANO_API_KEY")
    nano_model: str = os.getenv("NANO_MODEL", "google/nano-banana-edit")


settings = Settings()

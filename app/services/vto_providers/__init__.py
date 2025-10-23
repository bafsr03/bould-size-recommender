from .base import TryOnProvider
from .mock import MockTryOnProvider


def get_provider(name: str) -> TryOnProvider:
    name = (name or "mock").lower()
    if name == "mock":
        return MockTryOnProvider()
    if name in ("nano", "nanobanana", "nano-banana"):
        # Note: requires URLs and API key; see provider implementation
        from .nanobanana import NanoBananaProvider  # local import to avoid module at import time
        return NanoBananaProvider()  # type: ignore
    return MockTryOnProvider()

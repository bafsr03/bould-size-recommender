from .base import TryOnProvider
from .mock import MockTryOnProvider
from .nanobanana import NanoBananaProvider


def get_provider(name: str) -> TryOnProvider:
    name = (name or "mock").lower()
    if name == "mock":
        return MockTryOnProvider()
    if name in ("nano", "nanobanana", "nano-banana"):
        # Note: requires URLs and API key; see provider implementation
        return NanoBananaProvider()  # type: ignore
    return MockTryOnProvider()

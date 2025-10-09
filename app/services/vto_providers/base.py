from typing import Protocol


class TryOnProvider(Protocol):
    async def generate(self, user_image_path: str, garment_image_path: str) -> str:  # returns output file path
        ...

import os
from PIL import Image
import uuid
from ..config import settings


class MockTryOnProvider:
    async def generate(self, user_image_path: str, garment_image_path: str) -> str:
        os.makedirs(settings.storage_dir, exist_ok=True)
        try:
            user_img = Image.open(user_image_path).convert("RGB")
            garment_img = Image.open(garment_image_path).convert("RGB")
        except Exception:
            # If open fails, return an empty placeholder
            out_path = os.path.join(settings.storage_dir, f"tryon_{uuid.uuid4().hex}.jpg")
            Image.new("RGB", (512, 512), color=(200, 200, 200)).save(out_path, format="JPEG")
            return out_path

        # Resize garment image to match user height proportionally
        target_h = user_img.height
        ratio = target_h / max(1, garment_img.height)
        garment_resized = garment_img.resize((int(garment_img.width * ratio), target_h))

        # Compose side-by-side
        out_w = user_img.width + garment_resized.width
        out_h = max(user_img.height, garment_resized.height)
        canvas = Image.new("RGB", (out_w, out_h), color=(240, 240, 240))
        canvas.paste(user_img, (0, 0))
        canvas.paste(garment_resized, (user_img.width, 0))

        out_path = os.path.join(settings.storage_dir, f"tryon_{uuid.uuid4().hex}.jpg")
        canvas.save(out_path, format="JPEG", quality=90)
        return out_path

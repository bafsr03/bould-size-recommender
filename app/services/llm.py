from typing import Dict
import os

try:
    from openai import AsyncOpenAI
except Exception:
    AsyncOpenAI = None  # type: ignore

from ..config import settings


class TailorLLM:
    def __init__(self) -> None:
        self.api_key = settings.openai_api_key
        self.client = AsyncOpenAI(api_key=self.api_key) if (self.api_key and AsyncOpenAI) else None

    async def generate_feedback(self, category_id: int, body: Dict[str, float], garment: Dict[str, float], slacks: Dict[str, float], size: str, tone: str | None = None) -> str:
        # If no client available, produce deterministic rule-based feedback
        if not self.client:
            parts = []
            tight = [k for k, v in slacks.items() if v < 0]
            loose = [k for k, v in slacks.items() if v > 2.0]
            if tight:
                parts.append(f"Areas likely tight: {', '.join(tight)}.")
            if loose:
                parts.append(f"Areas with generous ease: {', '.join(loose)}.")
            parts.append(f"Recommended size: {size}.")
            parts.append("Consider tailoring: take-in where loose; let-out or size up if tight.")
            return " ".join(parts)

        prompt = (
            "You are an expert clothing tailor. Given body measurements, garment measurements for a selected size, and slacks (garment - (body + ease)), "
            "write a short, plain-language fitting note (<=80 words). Include what fits, what is tight/loose, and one alteration suggestion."
        )
        if tone:
            prompt += f"\n\nTone/Style: {tone}"

        content = {
            "category_id": category_id,
            "recommended_size": size,
            "slacks_cm": slacks,
        }
        try:
            resp = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": str(content)},
                ],
                temperature=0.3,
                max_tokens=120,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception:
            # Fallback on any error
            return f"Recommended size: {size}. If any area feels tight (negative slack), consider sizing up or minor alterations."


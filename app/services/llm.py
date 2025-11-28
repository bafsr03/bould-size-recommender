from typing import Dict, Any
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

    async def generate_feedback(self, category_id: int, body: Dict[str, float], garment: Dict[str, float], slacks: Dict[str, float], size: str, tone: str | None = None) -> Dict[str, Any]:
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
            
            return {
                "preview": [
                    f"Analyzing fit for size {size}...",
                    "Checking measurements against your profile...",
                    "Preparing your personalized fit report..."
                ],
                "final": " ".join(parts) + " Consider tailoring: take-in where loose; let-out or size up if tight."
            }

        prompt = (
            "You are an expert clothing tailor. Given body measurements, garment measurements for a selected size, and slacks (garment - (body + ease)), "
            "provide your feedback in a JSON object with two keys:\n"
            "1. 'preview': A list of exactly 3 short, distinct sentences (max 15 words each) to be displayed while the user waits. These should be engaging and relevant to the analysis process (e.g., 'Checking chest fit...', 'Analyzing sleeve length...').\n"
            "2. 'final': A single detailed paragraph (max 60 words) summarizing the fit. Include what fits well, what is tight/loose, and one specific alteration suggestion.\n"
            "Do not include markdown formatting, just the raw JSON."
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
                max_tokens=250,
                response_format={"type": "json_object"}
            )
            raw_content = (resp.choices[0].message.content or "").strip()
            import json
            return json.loads(raw_content)
        except Exception:
            # Fallback on any error
            return {
                "preview": [
                    f"Analyzing fit for size {size}...",
                    "Checking measurements against your profile...",
                    "Preparing your personalized fit report..."
                ],
                "final": f"Recommended size: {size}. If any area feels tight (negative slack), consider sizing up or minor alterations."
            }


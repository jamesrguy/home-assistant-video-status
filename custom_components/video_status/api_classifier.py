"""OpenRouter vision-API classifier for Video Status."""
from __future__ import annotations

import base64
import io
import json
import logging

import aiohttp
from PIL import Image

_LOGGER = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class APIClassifier:
    """Classify images by sending them to an OpenRouter vision model."""

    def __init__(self, api_key: str, model: str, states: list[str]) -> None:
        self.api_key = api_key
        self.model = model
        self.states = states

    async def classify(
        self, image: Image.Image
    ) -> tuple[str, float, dict[str, float]]:
        """Send *image* to the API and return (state, confidence, scores)."""
        img_buf = io.BytesIO()
        image.save(img_buf, format="JPEG", quality=85)
        img_b64 = base64.b64encode(img_buf.getvalue()).decode()

        states_str = ", ".join(f'"{s}"' for s in self.states)

        prompt = (
            f"Analyze this camera image and determine which of these states "
            f"best describes what you see: {states_str}.\n\n"
            f"Respond with ONLY a JSON object — no markdown, no explanation:\n"
            f'{{"state": "<one of the states>", "confidence": <0.0-1.0>}}'
        )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_b64}",
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 150,
            "temperature": 0.1,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                OPENROUTER_URL, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    _LOGGER.error("OpenRouter %d: %s", resp.status, body[:500])
                    raise ConnectionError(f"OpenRouter returned {resp.status}")
                result = await resp.json()

        content = result["choices"][0]["message"]["content"]

        # Strip markdown fences if present
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        parsed = json.loads(content.strip())
        state = str(parsed["state"])
        confidence = float(parsed.get("confidence", 0.5))

        # Normalise to a known state
        if state not in self.states:
            lower_map = {s.lower(): s for s in self.states}
            state = lower_map.get(state.lower(), self.states[0])
            if state == self.states[0]:
                confidence = 0.0

        # Build full score dict
        scores: dict[str, float] = {}
        remaining = 1.0 - confidence
        others = [s for s in self.states if s != state]
        per_other = remaining / max(len(others), 1)
        for s in self.states:
            scores[s] = confidence if s == state else per_other

        return state, confidence, scores

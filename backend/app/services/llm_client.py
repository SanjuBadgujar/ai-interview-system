"""
Thin wrapper around the Mistral client so the rest of the app depends on
a small interface (complete / stream) rather than the SDK directly.
"""
from typing import AsyncIterator
from app.core.config import settings

try:
    from mistralai import Mistral
except ImportError:  # allows the app to boot before deps are installed
    Mistral = None


class LLMClient:
    def __init__(self):
        self._client = Mistral(api_key=settings.mistral_api_key) if Mistral and settings.mistral_api_key else None
        self.model = settings.mistral_model

    async def complete(self, prompt: str, system: str | None = None) -> str:
        if not self._client:
            return self._mock_response(prompt)

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        resp = await self._client.chat.complete_async(
            model=self.model,
            messages=messages,
        )
        return resp.choices[0].message.content

    async def stream(self, prompt: str, system: str | None = None) -> AsyncIterator[str]:
        """Yields text deltas as they arrive, so the caller (interview
        websocket) can start chunking + TTS before the full reply lands."""
        if not self._client:
            for word in self._mock_response(prompt).split(" "):
                yield word + " "
            return

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        stream_resp = await self._client.chat.stream_async(
            model=self.model,
            messages=messages,
        )
        async for chunk in stream_resp:
            delta = chunk.data.choices[0].delta.content
            if delta:
                yield delta

    @staticmethod
    def _mock_response(prompt: str) -> str:
        """Deterministic placeholder so the app runs end-to-end with no
        API key configured — swap in real MISTRAL_API_KEY for real output."""
        return (
            "That's a good answer. Can you tell me more about how you "
            "approached that problem and what trade-offs you considered?"
        )


llm_client = LLMClient()

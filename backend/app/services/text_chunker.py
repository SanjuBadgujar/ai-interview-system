import re
from app.core.config import settings


class StreamingChunker:
    """Buffers text and yields sentence/clause chunks (~40-120 chars) split on
    punctuation boundaries, so TTS and audio playback can start immediately
    for the first sentence without waiting for full text."""

    SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+|(?<=[,;])\s+")

    def __init__(self, char_limit: int | None = None, min_chars: int | None = None):
        self.char_limit = char_limit or settings.tts_chunk_char_limit
        self.min_chars = min_chars or settings.tts_chunk_min_chars
        self._buffer = ""

    def feed(self, delta: str) -> list[str]:
        """Add text delta; return complete chunks ready for TTS."""
        self._buffer += delta
        chunks = []

        while True:
            parts = self.SPLIT_PATTERN.split(self._buffer)
            if len(parts) <= 1:
                break

            take = parts[0].strip()
            idx = 1
            while idx < len(parts) - 1 and len(take) < self.min_chars:
                take = (take + " " + parts[idx]).strip()
                idx += 1

            if len(take) >= self.min_chars or len(self._buffer) >= self.char_limit:
                chunks.append(take)
                self._buffer = self._buffer[len(take):].lstrip()
            else:
                break

        return chunks

    def flush(self) -> str | None:
        """Call once the stream ends to get any trailing partial chunk."""
        remainder = self._buffer.strip()
        self._buffer = ""
        return remainder or None


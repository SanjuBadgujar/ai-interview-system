"""
TTS via ElevenLabs API with key rotation.
"""
import asyncio
import logging
from elevenlabs.client import ElevenLabs
from app.core.config import settings

_logger = logging.getLogger(__name__)

class ElevenLabsKeyManager:
    def __init__(self):
        keys_str = settings.elevenlabs_api_keys or settings.elevenlabs_api_key or ""
        self.keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        self.current_index = 0
        self._lock = asyncio.Lock()
    
    def get_current_client(self):
        if not self.keys:
            raise ValueError("No ElevenLabs API keys configured")
        return ElevenLabs(api_key=self.keys[self.current_index])
    
    async def rotate_on_failure(self):
        async with self._lock:
            self.current_index = (self.current_index + 1) % len(self.keys)
            return self.current_index != 0

_key_manager = ElevenLabsKeyManager()
_voice_id = None

async def _ensure_voice_id():
    global _voice_id
    if _voice_id is None:
        _voice_id = settings.elevenlabs_voice_id

async def warmup_tts():
    await _ensure_voice_id()

async def synthesize_chunk(text: str) -> bytes:
    text = text.strip()
    if not text:
        return b""

    # The frontend supplies the selected system voice when browser TTS is the
    # configured provider. Returning no bytes intentionally activates that
    # primary path without making an ElevenLabs API call.
    if settings.tts_provider.lower() == "browser":
        return b""
    
    await warmup_tts()
    
    for attempt in range(len(_key_manager.keys)):
        try:
            client = _key_manager.get_current_client()
            # Use convert which returns Iterator[bytes]
            audio_iterator = await asyncio.to_thread(
                client.text_to_speech.convert,
                voice_id=_voice_id,
                text=text,
                model_id=settings.elevenlabs_model or "eleven_multilingual_v2",
                output_format=settings.elevenlabs_output_format or "pcm_16000",
            )
            # Collect all bytes from iterator
            audio_chunks = []
            for chunk in audio_iterator:
                audio_chunks.append(chunk)
            return b"".join(audio_chunks)
        except Exception as e:
            _logger.warning("ElevenLabs key %d failed: %s", _key_manager.current_index + 1, e)
            if "quota" in str(e).lower() or "401" in str(e) or "403" in str(e) or "429" in str(e):
                await _key_manager.rotate_on_failure()
                continue
            _logger.exception("ElevenLabs synthesis failed")
            return b""
    
    _logger.error("All ElevenLabs keys exhausted")
    return b""

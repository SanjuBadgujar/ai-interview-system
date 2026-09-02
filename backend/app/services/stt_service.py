"""
STT via Deepgram API with key rotation.
Uses the pre-recorded transcription endpoint which fits the segmented
audio chunks from VAD. Maintains a list of API keys and rotates on failure.
"""
import asyncio
import logging
from deepgram import DeepgramClient
from app.core.config import settings

_logger = logging.getLogger(__name__)

# Constants needed by voice_ws.py (match old Whisper values for compatibility)
_MIN_SAMPLES = 8000 + 32
_LIVE_MIN_SAMPLES = 8000 + 32


def _pcm16_bytes_to_float32(audio_bytes):
    """Compatibility stub - no longer used with Deepgram."""
    import numpy as np
    if len(audio_bytes) == 0:
        return np.zeros(0, dtype=np.float32)
    pcm16 = np.frombuffer(audio_bytes, dtype=np.int16)
    return pcm16.astype(np.float32) / 32768.0


def _is_mostly_silence(audio_array, threshold=0.015):
    """Compatibility stub - no longer used with Deepgram."""
    import numpy as np
    if audio_array.size == 0:
        return True
    rms = np.sqrt(np.mean(audio_array ** 2))
    return rms < threshold


class DeepgramKeyManager:
    def __init__(self):
        keys_str = settings.deepgram_api_keys or settings.deepgram_api_key or ""
        self.keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        self.current_index = 0
        self._lock = asyncio.Lock()
    
    def get_current_client(self):
        if not self.keys:
            raise ValueError("No Deepgram API keys configured")
        return DeepgramClient(api_key=self.keys[self.current_index])
    
    async def rotate_on_failure(self):
        async with self._lock:
            self.current_index = (self.current_index + 1) % len(self.keys)
            return self.current_index != 0

_key_manager = DeepgramKeyManager()


def transcribe_audio_bytes(audio_bytes, *, live=False):
    if len(audio_bytes) == 0:
        return ""
    
    min_samples = _LIVE_MIN_SAMPLES if live else _MIN_SAMPLES
    if len(audio_bytes) < min_samples * 2:
        return ""

    for attempt in range(len(_key_manager.keys)):
        try:
            client = _key_manager.get_current_client()
            response = client.listen.v1.media.transcribe_file(
                request=audio_bytes,
                # The v7 SDK accepts API values directly.  Its generated enum no
                # longer exposes LINEAR16, which otherwise fails before any
                # transcription request is sent.
                encoding="linear16",
                model=settings.deepgram_model or "nova-2",
                language="en",
                smart_format=True,
                punctuate=True,
                # Deepgram's v7 generated media client does not expose raw
                # PCM metadata as keyword arguments. Send the required sample
                # rate through its supported request-options escape hatch.
                request_options={
                    "additional_query_parameters": {"sample_rate": 16000}
                },
            )
            
            results = response.results if hasattr(response, "results") else None
            if results and results.channels:
                for channel in results.channels:
                    if channel.alternatives:
                        transcript = channel.alternatives[0].transcript.strip()
                        if transcript:
                            return transcript
            return ""
        except Exception as e:
            _logger.warning("Deepgram key %d failed: %s", _key_manager.current_index + 1, e)
            if "quota" in str(e).lower() or "401" in str(e) or "403" in str(e):
                asyncio.run(_key_manager.rotate_on_failure())
                continue
            _logger.exception("Deepgram transcription failed")
            return ""
    
    _logger.error("All Deepgram keys exhausted")
    return ""


async def transcribe_audio_bytes_async(audio_bytes, *, live=False):
    return await asyncio.to_thread(transcribe_audio_bytes, audio_bytes, live=live)

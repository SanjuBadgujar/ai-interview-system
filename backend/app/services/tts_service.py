"""
TTS via Kyutai's Pocket TTS — a 100M-param, CPU-only, open-source model
(https://github.com/kyutai-labs/pocket-tts). Runs fully locally, no API
key needed. Weights + the chosen voice are downloaded automatically from
Hugging Face on first use and cached (~/.cache/huggingface by default)
for every run after that.

Model load and voice-state prep are both slow-ish one-time operations,
so both are cached as module-level singletons and reused across every
chunk/question/interview. generate_audio() itself is a blocking CPU call
(no native async support), so we run it in a worker thread via
asyncio.to_thread to avoid blocking the event loop / other WS clients.
"""
import asyncio
import io
from app.core.config import settings

_model = None
_voice_state = None
_lock = asyncio.Lock()


def _load_model_and_voice():
    """Blocking setup — first call downloads model + voice weights."""
    from pocket_tts import TTSModel

    model = TTSModel.load_model()
    voice_state = model.get_state_for_audio_prompt(settings.tts_voice)
    return model, voice_state


async def _ensure_loaded():
    global _model, _voice_state
    if _model is not None:
        return
    async with _lock:
        if _model is None:  # re-check inside the lock
            _model, _voice_state = await asyncio.to_thread(_load_model_and_voice)


def _synthesize_blocking(text: str) -> bytes:
    """Runs on a worker thread. Returns WAV bytes (so the frontend can
    decode them with the Web Audio API's decodeAudioData as-is)."""
    import scipy.io.wavfile

    audio_tensor = _model.generate_audio(_voice_state, text)
    audio_np = audio_tensor.numpy()

    buffer = io.BytesIO()
    scipy.io.wavfile.write(buffer, _model.sample_rate, audio_np)
    return buffer.getvalue()


async def synthesize_chunk(text: str) -> bytes:
    """Convert one small text chunk (~150 chars) to WAV audio bytes for
    immediate playback. Called once per chunk from the chunker so audio
    can start before the full LLM response has finished streaming."""
    text = text.strip()
    if not text:
        return b""

    if settings.tts_provider != "pocket":
        raise ValueError(f"Unknown TTS provider: {settings.tts_provider}")

    await _ensure_loaded()
    return await asyncio.to_thread(_synthesize_blocking, text)

"""
STT via Whisper (faster-whisper or openai-whisper).
Loaded lazily since the model is large; first call pays the load cost,
subsequent calls reuse the in-memory model with thread serialization.

IMPORTANT: this skips ffmpeg entirely. The frontend (useVoiceInterview.js)
already sends raw 16kHz mono PCM16 samples, so we convert those bytes to
the float32 array Whisper expects ourselves and pass the array directly
via `transcribe(audio=...)`.
"""
import asyncio
import threading
import numpy as np
from app.core.config import settings

_model = None
_model_lock = threading.Lock()
_is_faster_whisper = False


def _get_model():
    global _model, _is_faster_whisper
    if _model is None:
        try:
            from faster_whisper import WhisperModel
            _model = WhisperModel(
                settings.whisper_model,
                device="cpu",
                compute_type="int8",
                cpu_threads=4,
            )
            _is_faster_whisper = True
        except Exception:
            import whisper
            _model = whisper.load_model(settings.whisper_model)
            _is_faster_whisper = False
    return _model


def _pcm16_bytes_to_float32(audio_bytes: bytes) -> np.ndarray:
    """Convert raw 16-bit PCM bytes (little-endian, mono, 16kHz) into the
    normalized float32 array Whisper expects, with no ffmpeg/file I/O."""
    if len(audio_bytes) == 0:
        return np.zeros(0, dtype=np.float32)
    pcm16 = np.frombuffer(audio_bytes, dtype=np.int16)
    return pcm16.astype(np.float32) / 32768.0


def _is_mostly_silence(audio_array: np.ndarray, threshold: float = 0.015) -> bool:
    """Return True if the audio is mostly silence (RMS below threshold).
    Avoids wasting Whisper on noise/background chunks."""
    if audio_array.size == 0:
        return True
    rms = np.sqrt(np.mean(audio_array ** 2))
    return rms < threshold


# Minimum samples to transcribe (0.5s of 16kHz = 8000 samples).
_MIN_SAMPLES = 8000 + 32
_LIVE_MIN_SAMPLES = 8000 + 32


def transcribe_audio_bytes(audio_bytes: bytes, *, live: bool = False) -> str:
    """Transcribe raw 16kHz mono PCM16 audio bytes. Thread-safe."""
    audio_array = _pcm16_bytes_to_float32(audio_bytes)
    min_samples = _LIVE_MIN_SAMPLES if live else _MIN_SAMPLES
    if audio_array.size < min_samples:
        return ""

    if live and _is_mostly_silence(audio_array):
        return ""

    model = _get_model()
    try:
        with _model_lock:
            if _is_faster_whisper:
                segments, info = model.transcribe(
                    audio_array,
                    beam_size=1,
                    language="en",
                    vad_filter=True,
                    condition_on_previous_text=False,
                    no_speech_threshold=0.6,
                )
                parts = []
                for seg in segments:
                    if getattr(seg, "no_speech_prob", 0) > 0.5:
                        continue
                    text = seg.text.strip()
                    if text:
                        parts.append(text)
                return " ".join(parts).strip()
            else:
                options = {
                    "fp16": False,
                    "language": "en",
                    "no_speech_threshold": 0.6,
                    "condition_on_previous_text": False,
                }
                result = model.transcribe(audio=audio_array, **options)
                segments = result.get("segments", [])
                parts = []
                for seg in segments:
                    if seg.get("no_speech_prob", 0) > 0.5:
                        continue
                    text = seg.get("text", "").strip()
                    if text:
                        parts.append(text)
                if parts:
                    return " ".join(parts).strip()
                res_text = result.get("text", "").strip()
                return res_text if not _is_mostly_silence(audio_array, 0.02) else ""

    except Exception:
        import logging
        logging.getLogger("stt").exception(
            "Whisper failed on a {:.2f}s audio slice".format(
                audio_array.size / 16000.0
            )
        )
        return ""


async def transcribe_audio_bytes_async(audio_bytes: bytes, *, live: bool = False) -> str:
    """Async wrapper around transcribe_audio_bytes. Runs on a worker thread with lock."""
    return await asyncio.to_thread(transcribe_audio_bytes, audio_bytes, live=live)


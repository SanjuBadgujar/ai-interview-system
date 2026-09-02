"""
Real-time voice loop with turn-taking:

  Turn state machine:
    [AI speaks question TTS] -> (audio ends; frontend sends audio_end)
    -> USER_LISTENING (mic on, backend VADs user audio)
    -> 2s pause (SEGMENT_DONE) -> answer committed, transcript sent
       -> speak the (pre-generated) next question instantly -> AI speaks -> ... repeats
    -> empty answer (nothing understood) -> keep current question, re-listen

All question text is generated up-front (see /interview/start and
generate_all_question_texts), so the next question is available instantaneously
with no LLM call during the live conversation. There is no early-LLM overlap.

The backend only VADs/transcribes user audio while it is "awaiting an answer"
(awaiting_answer is True). Audio received while the AI is speaking is dropped
silently, so the AI's own TTS echo from the speakers can never be mistaken for a
user answer.

The "answer done" trigger is a configurable long silence (default ~2s).

Wire format (simple, JSON-control + binary-audio):
  Client -> Server:
    - binary frames: raw 16kHz mono PCM audio (candidate speaking) [only
      meaningful while the backend is awaiting an answer]
    - {"type": "audio_end"} : AI playback finished -> backend starts
      accepting user audio (turn: USER_LISTENING)
    - {"type": "end_of_answer"} : force-flush if not relying on VAD alone
  Server -> Client:
    - {"type": "transcript", "role": "candidate", "text": "..."}  (finalized answer)
    - For each TTS chunk, together (in seq order):
        {"type": "ai_text", "seq": N, "text": "..."}
        {"type": "audio_chunk", "seq": N, "text": "..."}
        followed immediately by a binary frame of that chunk's audio,
        so text for a chunk is revealed exactly when its audio speaks
    - {"type": "ai_response", "text": "..."}  (the complete question, after all audio)
    - {"type": "question_complete"}  (sentinel: audio + ai_text all delivered)
    - {"type": "listening"}  (empty answer -> backend re-armed; open the mic again)
    - {"type": "interview_complete"}
"""
import asyncio
import json
import logging
import random
import re

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.models.state import store
from app.services.vad_service import (
    SilenceTracker,
    SPEECH,
    SEGMENT_DONE,
    UTTERANCE_DONE,
    PROMPT_TIMEOUT,
    IDLE_TIMEOUT,
)
from app.services.stt_service import (
    transcribe_audio_bytes_async,
    _pcm16_bytes_to_float32,
    _is_mostly_silence,
    _MIN_SAMPLES,
    _LIVE_MIN_SAMPLES,
)
from app.services.text_chunker import StreamingChunker
from app.services.tts_service import synthesize_chunk
from app.services.interview_planner import ensure_question_generated

router = APIRouter()

logger = logging.getLogger("voice_ws")

FRAMES_PER_SECOND = 50  # ~20ms frames
FRAME_BYTES = 320  # one 20ms frame @ 16kHz mono 16-bit PCM

# Voice command patterns — matched against the full transcript text
_REPEAT_PATTERNS = re.compile(
    r"^\s*(repeat|come again|say again|once more|pardon|can you repeat|repeat question|what was that|can you repeat the question|once again|say that again|what did you say|say it again|repeat that|one more time)\s*[.?!]?\s*$",
    re.IGNORECASE,
)

_SKIP_PATTERNS = re.compile(
    r"^\s*(move on|next question|skip|pass|next|I don't know|dunno|no idea|let's move|(?:can you |please )?(?:move|go)(?: on| in| to| with)?(?: the)? next(?: question)?|I(?:'m| am) (?:gonna|going to) move(?: with| to)?(?: the)? next(?: question)?|I don't know the answer)\s*[.?!]?\s*$",
    re.IGNORECASE,
)

# Brief acknowledgements spoken after a normal answer before the next question
_ACKNOWLEDGEMENTS = [
    "Got it.",
    "Okay, understood.",
    "Makes sense.",
    "Alright.",
    "Noted.",
    "Okay, got it.",
    "I see.",
    "Understood.",
]

# Brief acknowledgements spoken when the user skips a question
_SKIP_ACKNOWLEDGEMENTS = [
    "No worries, let's move on.",
    "That's okay, next question.",
    "Alright, moving on.",
    "No problem, let's continue.",
]


def _debug(msg: str):
    """Debug line for diagnosing the real-time voice loop (VAD, turn state,
    transcripts). Comment out or replace with logger.info/logger.debug as needed."""
    logger.info("[voice] %s", msg)
    print("[voice]", msg)


def _detect_voice_command(text: str) -> str | None:
    """Classify transcribed text as a voice command. Returns 'repeat', 'skip',
    or None for a normal answer."""
    text = text.strip()
    if _REPEAT_PATTERNS.match(text):
        return "repeat"
    if _SKIP_PATTERNS.match(text):
        return "skip"
    return None


def _utterance_frames() -> int:
    return max(1, int(round(settings.stt_silence_seconds * FRAMES_PER_SECOND)))


def _segment_frames() -> int:
    """Number of ~20ms frames (~320 bytes each) before a short pause finalizes a
    live-STT chunk. Must stay below the utterance-silence frame count."""
    return max(1, int(round(settings.stt_segment_seconds * FRAMES_PER_SECOND)))


def _prompt_timeout_frames() -> int:
    """Number of ~20ms frames before we send "Are you still there?" prompt."""
    return max(1, int(round(settings.stt_prompt_timeout_seconds * FRAMES_PER_SECOND)))


def _idle_timeout_frames() -> int:
    """Frames with no candidate speech before moving to the next question."""
    return max(1, int(round(settings.stt_no_answer_timeout_seconds * FRAMES_PER_SECOND)))


def _segment_tail_bytes() -> int:
    """Bytes of trailing silence buffered before SEGMENT_DONE fires. That tail is
    silence by construction (exactly `segment_frames` silent frames are appended
    before the pause is long enough to finalize a chunk); trimming it before
    transcription keeps Whisper from hallucinating filler on low-signal / noise-
    tail audio. Use a 1-frame margin so we never clip into real speech."""
    return (_segment_frames() + 1) * FRAME_BYTES


def _max_chunk_bytes() -> int:
    """Max audio bytes (16kHz mono 16-bit = 32000 B/s) per Whisper call."""
    return max(1, int(round(settings.stt_max_chunk_seconds * 16000 * 2)))


# Whisper's classic hallucination filler phrases. On low-signal / silence-tail
# audio it emits these as their own isolated block. Only dropped when a chunk's
# ENTIRE text is one of these (conservative), so genuine words inside a phrase
# are never removed.
_FILLER_PHRASES = (
    "uh", "um", "uhh", "umm", "mm", "hmm", "mhm",
    "thank you", "thanks", "thank you for watching", "watching",
    "bye", "by", "you", "ok", "okay", "so", "ok so",
    "the", "a", "i", "i i", "you you",
    "hello", "hello hello",
    "bye daddy", "okay so bye", "ok so bye", "bye bye",
    "for application code", "application code",
    "subtitles by", "amara.org",
)


def _is_hallucination_or_filler(text: str) -> bool:
    if not text:
        return True
    norm = text.lower().strip(" .,!?\"'")
    if not norm:
        return True
    if norm in _FILLER_PHRASES:
        return True
    return False


def _join_chunk_texts(chunk_results: dict[int, str]) -> str:
    """Join the per-chunk STT blocks into the final answer.

    - Collapses runs of consecutive identical chunks (Whisper echoes a short
      phrase across adjacent sub-chunks of one utterance).
    - Drops isolated hallucination filler chunks (see _FILLER_PHRASES). Only a
      chunk whose entire text is a known filler is removed, so "Thank you." said
      for real inside a longer sentence is preserved.
    Returns the space-joined answer string (or "" if nothing survived)."""
    parts = []
    prev_norm = None
    for k in sorted(chunk_results):
        text = chunk_results[k].strip()
        if not text:
            continue
        norm = text.lower().strip(" .,!?")
        if norm == prev_norm:
            continue
        prev_norm = norm
        if _is_hallucination_or_filler(text):
            continue
        parts.append(text)
    return " ".join(parts).strip()


class _Socket:
    """Thin wrapper around a WebSocket that never raises on a closed socket.
    Every send goes through this, so background tasks (STT, TTS) and the main
    loop can't crash the ASGI app with a RuntimeError once the client has
    disconnected mid-turn."""

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.closed = False
        # Serialize every send on the underlying socket. STT/TTS tasks and the
        # main loop all send concurrently; without a lock two concurrent send_json
        # calls on the same Starlette WebSocket can raise a RuntimeError, which was
        # being misread as a disconnect and permanently muted the (still-open)
        # socket so the next question never reached the client.
        self._send_lock = asyncio.Lock()

    def is_open(self) -> bool:
        from starlette.websockets import WebSocketState
        return not self.closed and self.websocket.client_state == WebSocketState.CONNECTED

    async def _guard(self, coro):
        if self.closed:
            return False
        try:
            await coro
            return True
        except (RuntimeError, WebSocketDisconnect):
            # Only treat it as closed if the underlying socket is really gone.
            # A transient error while still CONNECTED must not poison the socket.
            self.closed = not self.is_open()
            return False

    async def send_json(self, payload: dict) -> bool:
        async with self._send_lock:
            if self.closed:
                return False
            return await self._guard(self.websocket.send_json(payload))

    async def send_bytes(self, data: bytes) -> bool:
        async with self._send_lock:
            if self.closed:
                return False
            return await self._guard(self.websocket.send_bytes(data))


@router.websocket("/interview/voice/{interview_id}")
async def voice_ws(websocket: WebSocket, interview_id: str):
    await websocket.accept()
    sock = _Socket(websocket)

    session = store.get_session(interview_id)
    if not session:
        await sock.send_json({"type": "error", "message": "interview_id not found"})
        await websocket.close()
        return
    _debug(f"connected interview_id={interview_id}")

    # Turn-taking state: backend only processes user audio while True. Starts
    # False; becomes True when the frontend says AI playback ended (audio_end).
    turn = {
        "awaiting": False,
        "reassured": False,
    }

    # Question #1 was pre-generated by POST /interview/start — speak it now,
    # once, so the candidate actually hears an opening question.
    if not session.first_question_voiced:
        first_item = session.plan.questions[0]
        if first_item.question_text:
            await _speak_question(sock, session, first_item)
        session.first_question_voiced = True
        _debug("spoke question #1; awaiting_answer still False until client sends audio_end")

    silence_tracker = SilenceTracker(
        silence_frames_threshold=_utterance_frames(),
        segment_frames_threshold=_segment_frames(),
        prompt_timeout_frames=_prompt_timeout_frames(),
        idle_timeout_frames=_idle_timeout_frames(),
    )
    audio_buffer = bytearray()

    # chunk-based live STT state for the CURRENT answer
    pending_tasks: list[asyncio.Task] = []
    chunk_results: dict[int, str] = {}
    chunk_seq = 0
    vad_state_counts: dict[str, int] = {}

    # Bound Whisper concurrency so many parallel transcriptions can't saturate
    # the CPU (which starved the websocket pings and dropped the connection on
    # long answers).
    stt_semaphore = asyncio.Semaphore(settings.stt_max_concurrency)

    last_chunk_offset = 0

    try:
        while True:
            message = await websocket.receive()

            if "bytes" in message and message["bytes"] is not None:
                frame = message["bytes"]

                # Drop audio silently while not awaiting an answer (mic off while
                # the AI speaks; any stray/echo frames must not VAD into a fake
                # empty answer or a runaway question loop).
                if not turn["awaiting"]:
                    continue

                audio_buffer.extend(frame)
                state = silence_tracker.process_frame(frame)
                vad_state_counts[state] = vad_state_counts.get(state, 0) + 1

                # If speech hasn't started yet for this turn, cap audio_buffer to ~300ms leading audio
                # (15 frames = 4800 bytes) so background room noise doesn't accumulate before speech.
                if not silence_tracker.has_spoken:
                    max_pre_speech = 15 * FRAME_BYTES
                    if len(audio_buffer) > max_pre_speech:
                        del audio_buffer[:-max_pre_speech]
                        last_chunk_offset = 0

                if state == SEGMENT_DONE:
                    _debug(
                        f"SEGMENT_DONE -> transcribing chunk slice; incurred speech="
                        f"{vad_state_counts.get(SPEECH, 0)}"
                    )
                    new_data = bytes(audio_buffer[last_chunk_offset:])
                    tail = _segment_tail_bytes()
                    if len(new_data) > tail:
                        new_data = new_data[:-tail]
                    # Thresholds in stt_service are expressed in PCM samples;
                    # the websocket buffer holds 16-bit PCM bytes.
                    if len(new_data) >= _LIVE_MIN_SAMPLES * 2:
                        last_chunk_offset = len(audio_buffer)
                        cap = _max_chunk_bytes()
                        for start in range(0, len(new_data), cap):
                            piece = new_data[start:start + cap]
                            seq = chunk_seq
                            chunk_seq += 1
                            task = asyncio.create_task(
                                _transcribe_chunk(
                                    piece, seq, chunk_results, stt_semaphore,
                                )
                            )
                            pending_tasks.append(task)

                elif state == PROMPT_TIMEOUT:
                    if not turn["reassured"]:
                        _debug("PROMPT_TIMEOUT -> speaking reassurance prompt")
                        turn["reassured"] = True
                        await _speak_text(
                            sock,
                            "Take your time - no pressure. I'll wait a few more seconds before moving on.",
                            complete=False,
                            response_type="nudge",
                        )
                    continue

                elif state == IDLE_TIMEOUT:
                    _debug("IDLE_TIMEOUT -> no answer; moving to next question")
                    turn["awaiting"] = False
                    await _advance_after_no_answer(sock, session)
                    audio_buffer.clear()
                    last_chunk_offset = 0
                    pending_tasks = []
                    chunk_results = {}
                    chunk_seq = 0

                elif state == UTTERANCE_DONE:
                    _debug(
                        f"UTTERANCE_DONE -> answer committed; total frames: {dict(vad_state_counts)}"
                    )
                    vad_state_counts = {}
                    turn["awaiting"] = False
                    should_relisten = await _commit_answer(
                        sock, session, silence_tracker, audio_buffer,
                        pending_tasks, chunk_results,
                    )
                    # reset per-answer state
                    audio_buffer.clear()
                    last_chunk_offset = 0
                    pending_tasks = []
                    chunk_results = {}
                    chunk_seq = 0
                    if should_relisten and turn["reassured"]:
                        _debug("empty answer after reassurance -> moving to next question")
                        await _advance_after_no_answer(sock, session)
                    elif should_relisten:
                        _debug("empty answer -> re-arming listening")
                        turn["awaiting"] = True

            elif "text" in message and message["text"] is not None:
                payload = json.loads(message["text"])
                msg_type = payload.get("type")
                _debug(f"client message: {msg_type}")
                if msg_type == "audio_end":
                    turn["awaiting"] = True
                    turn["reassured"] = False
                    silence_tracker.reset()
                    audio_buffer.clear()
                elif msg_type == "end_of_answer":
                    turn["awaiting"] = False
                    should_relisten = await _commit_answer(
                        sock, session, silence_tracker, audio_buffer,
                        pending_tasks, chunk_results,
                    )
                    audio_buffer.clear()
                    pending_tasks = []
                    chunk_results = {}
                    chunk_seq = 0
                    if should_relisten:
                        turn["awaiting"] = True

    except WebSocketDisconnect:
        sock.closed = True
        _debug(f"disconnected interview_id={interview_id}")
    except RuntimeError:
        # already-closed socket raced a send; mark closed and stop cleanly
        sock.closed = True
        _debug(f"socket send failed (closed) interview_id={interview_id}")


async def _transcribe_chunk(
    data: bytes,
    seq: int,
    chunk_results: dict[int, str],
    semaphore: asyncio.Semaphore,
):
    """Transcribe one bounded speech chunk for final-answer fallback only."""
    try:
        async with semaphore:
            text = (await transcribe_audio_bytes_async(data, live=True)).strip()
    except Exception:
        _debug(f"STT chunk seq={seq} failed")
        return
    _debug(f"STT chunk seq={seq} bytes={len(data)} text={text!r}")
    if not text or _is_hallucination_or_filler(text):
        return
    chunk_results[seq] = text


async def _commit_answer(
    sock: _Socket,
    session,
    silence_tracker: SilenceTracker,
    audio_buffer: bytearray,
    pending_tasks: list[asyncio.Task],
    chunk_results: dict[int, str],
) -> bool:
    """Called when the answer is committed (UTTERANCE_DONE at 2.5s silence, or
    an explicit end_of_answer). Transcribes the ENTIRE accumulated audio buffer
    as one complete piece to Whisper for full-context accuracy."""
    if pending_tasks:
        # Finish any already-started live chunks before producing the one final
        # transcript. This preserves their text as a fallback if full-buffer STT
        # returns nothing, without sending fragmented text to the client.
        await asyncio.gather(*pending_tasks, return_exceptions=True)
        pending_tasks.clear()

    full_data = bytes(audio_buffer)
    audio_buffer.clear()

    _debug(f"committing answer with full audio buffer: {len(full_data)} bytes")

    answer_text = ""
    # _MIN_SAMPLES is a sample count while full_data is PCM16 bytes.
    if len(full_data) >= _MIN_SAMPLES * 2:
        res = (await transcribe_audio_bytes_async(full_data, live=False)).strip()
        if res and not _is_hallucination_or_filler(res):
            answer_text = res

    # Fallback to joined live chunks if full buffer transcription was empty
    if not answer_text and chunk_results:
        answer_text = _join_chunk_texts(chunk_results)

    silence_tracker.reset()
    _debug(f"finalize answer (full buffer {len(full_data)} bytes) -> {answer_text!r}")

    return await _produce_next_turn(sock, session, answer_text)



async def _produce_next_turn(sock: _Socket, session, answer_text: str) -> bool:
    """Turn the committed answer into the next AI question.

    Handles voice commands (repeat, skip) and adds brief acknowledgements
    combined with the question in a single TTS call.

    Returns True if the answer was empty (caller should re-arm listening and keep
    the current question), False otherwise."""
    command = _detect_voice_command(answer_text)

    # REPEAT: speak current question again (no ack), don't advance
    if command == "repeat":
        _debug("voice command: REPEAT")
        session.record("candidate", answer_text)
        await sock.send_json({"type": "transcript", "role": "candidate", "text": answer_text})
        item = session.current_question_item()
        if item:
            await _speak_question(sock, session, item)
        return False

    # SKIP: acknowledge briefly, advance to next question
    if command == "skip":
        _debug("voice command: SKIP")
        session.record("candidate", answer_text)
        await sock.send_json({"type": "transcript", "role": "candidate", "text": answer_text})
        session.advance()
        if session.is_complete:
            _debug("interview_complete")
            await sock.send_json({"type": "interview_complete"})
            return False
        item = session.current_question_item()
        await ensure_question_generated(item, session.resume, session.jd, prior_answer=answer_text)
        ack = random.choice(_SKIP_ACKNOWLEDGEMENTS)
        await _speak_question(sock, session, item, prefix=ack)
        # Pre-generate next question in background
        _pre_generate_next(session, answer_text)
        return False

    # EMPTY: re-listen
    if not answer_text:
        _debug("candidate answer is EMPTY")
        await sock.send_json({"type": "listening"})
        return True

    # NORMAL ANSWER: record, advance, ack + next question in one TTS call
    session.record("candidate", answer_text)
    await sock.send_json({"type": "transcript", "role": "candidate", "text": answer_text})
    _debug(f"candidate answer_text={answer_text!r} (len={len(answer_text)})")

    session.advance()
    if session.is_complete:
        _debug("interview_complete")
        await sock.send_json({"type": "interview_complete"})
        return False

    item = session.current_question_item()
    await ensure_question_generated(item, session.resume, session.jd, prior_answer=answer_text)
    ack = random.choice(_ACKNOWLEDGEMENTS)
    await _speak_question(sock, session, item, prefix=ack)
    # Pre-generate next question in background
    _pre_generate_next(session, answer_text)
    return False


async def _advance_after_no_answer(sock: _Socket, session) -> None:
    """Move on after the candidate remained silent through both idle windows."""
    session.advance()
    if session.is_complete:
        _debug("interview_complete after no-answer timeout")
        await sock.send_json({"type": "interview_complete"})
        return

    item = session.current_question_item()
    await ensure_question_generated(item, session.resume, session.jd, prior_answer="")
    await _speak_question(sock, session, item, prefix="Let's move to the next question")
    _pre_generate_next(session, "")


def _pre_generate_next(session, last_answer: str) -> None:
    """Pre-generate the NEXT question in the background while the user answers
    the current one. This hides the LLM latency behind user thinking time."""
    next_idx = session.current_index + 1
    if next_idx >= len(session.plan.questions):
        return
    next_item = session.plan.questions[next_idx]
    if next_item.question_text:
        return  # Already generated

    async def _do():
        try:
            await ensure_question_generated(
                next_item, session.resume, session.jd, prior_answer=last_answer
            )
            _debug(f"pre-generated Q{next_idx}: {next_item.question_text[:50]}...")
        except Exception:
            _debug(f"pre-generate failed for Q{next_idx}")

    asyncio.create_task(_do())


async def _speak_question(sock: _Socket, session, item, prefix: str = ""):
    """Chunk a question and synthesize/send its audio, revealing each chunk's
    text in sync with its audio. If prefix is provided (e.g. an acknowledgement),
    it is spoken before the question as part of the same audio stream.
    Short combined texts bypass the chunker to avoid splitting at punctuation."""
    question_text = item.question_text or "Could you tell me more about that?"
    if prefix:
        speak_text = f"{prefix.rstrip('. ')}... {question_text}"
    else:
        speak_text = question_text

    sender = _SequentialSender(sock)
    seq = 0

    # Short combined text → single chunk, no splitting (keeps audio seamless)
    if len(speak_text) <= settings.tts_chunk_char_limit:
        await _emit_chunk(sender, seq, speak_text)
    else:
        # Long text → use chunker to split at sentence boundaries
        chunker = StreamingChunker()
        for chunk in chunker.feed(speak_text):
            await _emit_chunk(sender, seq, chunk)
            seq += 1
        tail = chunker.flush()
        if tail:
            await _emit_chunk(sender, seq, tail)

    item.question_text = question_text
    session.record("ai", speak_text)
    await sock.send_json({"type": "ai_response", "text": speak_text})
    await sock.send_json({"type": "question_complete"})
    _debug(f"question complete (seqs={seq})")


async def _speak_text(
    sock: _Socket,
    text: str,
    *,
    complete: bool = True,
    response_type: str = "ai_response",
):
    """Speak a short text (acknowledgement) without recording or advancing.
    Uses the same TTS pipeline as _speak_question but skips session state."""
    sender = _SequentialSender(sock)
    chunker = StreamingChunker()
    seq = 0
    for chunk in chunker.feed(text):
        await _emit_chunk(sender, seq, chunk)
        seq += 1

    tail = chunker.flush()
    if tail:
        await _emit_chunk(sender, seq, tail)

    await sock.send_json({"type": response_type, "text": text})
    if complete:
        await sock.send_json({"type": "question_complete"})


class _SequentialSender:
    """Reveals each chunk's text (ai_text + audio_chunk text) together with its
    audio bytes, in strict seq order, so text and audio stay in sync."""

    def __init__(self, sock: _Socket):
        self.sock = sock
        self._next_seq = 0
        self._cond = asyncio.Condition()

    async def reveal(self, seq: int, text: str, audio_bytes: bytes):
        async with self._cond:
            # wake either when it is our turn, or when the socket closed
            await self._cond.wait_for(
                lambda: seq == self._next_seq or self.sock.closed
            )
            if self.sock.closed:
                return
            # text + audio together, in order
            await self.sock.send_json({"type": "ai_text", "seq": seq, "text": text})
            await self.sock.send_json(
                {
                    "type": "audio_chunk",
                    "seq": seq,
                    "text": text,
                    "has_audio": bool(audio_bytes),
                }
            )
            if audio_bytes:
                await self.sock.send_bytes(audio_bytes)
            _debug(f"reveal chunk seq={seq} text={text!r} audio_bytes={len(audio_bytes)}")
            self._next_seq += 1
            self._cond.notify_all()


async def _emit_chunk(sender: _SequentialSender, seq: int, text: str):
    """Synthesize one chunk's audio in the background, then reveal its text and
    audio together (in seq order)."""
    audio_bytes = await synthesize_chunk(text)
    await sender.reveal(seq, text, audio_bytes)

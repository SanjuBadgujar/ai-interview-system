"""
Voice Activity Detection using webrtcvad. Consumes 16-bit PCM mono audio
frames (recommended: 16kHz, 20-30ms frames) and tracks whether the
candidate is currently speaking, so the WebSocket handler knows when a
period of silence means "candidate finished answering."
"""
import webrtcvad

SPEECH = "speech"
SEGMENT_DONE = "segment_done"
START_AHEAD = "start_ahead"  # enough trailing silence to safely start the next LLM question early
UTTERANCE_DONE = "utterance_done"
PROMPT_TIMEOUT = "prompt_timeout"  # ~6s silence -> reassurance prompt
IDLE_TIMEOUT = "idle_timeout"  # no answer after the reassurance prompt


class SilenceTracker:
    """Tracks speech vs. silence to detect both the end of a short speech
    *segment* (a brief pause mid-answer, used for chunked live STT) and the
    end of the whole *utterance* (longer trailing silence).

    States:
      SPEECH          - currently speaking, keep buffering
      SEGMENT_DONE    - a brief pause ended a segment -> finalize & transcribe
                        that chunk now (near-real-time STT display)
      START_AHEAD     - enough trailing silence to start the next-question LLM
      PROMPT_TIMEOUT  - ~6s silence -> send the reassurance prompt
      UTTERANCE_DONE  - trailing silence after an answer -> commit it and move on
    """

    def __init__(
        self,
        aggressiveness: int = 2,
        silence_frames_threshold: int = 125,
        segment_frames_threshold: int = 20,
        start_ahead_frames_threshold: int = 60,
        prompt_timeout_frames: int = 300,
        idle_timeout_frames: int = 400,
        min_speech_frames: int = 3,
    ):
        """
        aggressiveness: 0-3, higher = more aggressive filtering of non-speech.
        silence_frames_threshold: consecutive silent frames (~20ms each) before
            we consider the candidate done with the whole answer.
        segment_frames_threshold: consecutive silent frames before we finalize
            one live-STT chunk. Must be < prompt_timeout_frames.
        prompt_timeout_frames: consecutive silent frames (~20ms each) before we
            send the "Are you still there?" prompt.
        min_speech_frames: consecutive speech frames (~20ms each) required to
            count as real speech (prevents single-frame noise ticks from resetting silence).
        """
        self.vad = webrtcvad.Vad(aggressiveness)
        self.silence_frames_threshold = silence_frames_threshold
        self.segment_frames_threshold = min(
            segment_frames_threshold, silence_frames_threshold - 1
        )
        self.prompt_timeout_frames = prompt_timeout_frames
        self.idle_timeout_frames = max(prompt_timeout_frames + 1, idle_timeout_frames)
        self.start_ahead_frames_threshold = min(
            start_ahead_frames_threshold, silence_frames_threshold - 1
        )
        self.min_speech_frames = min_speech_frames
        self._silence_run = 0
        self._speech_run = 0
        self._has_spoken = False
        self._prompt_sent = False
        self._segment_fired = False
        self._idle_silence_run = 0
        self._idle_prompt_sent = False

    def process_frame(self, frame: bytes, sample_rate: int = 16000) -> str:
        """Feed one audio frame and return the current tracker state."""
        is_speech = self.vad.is_speech(frame, sample_rate)

        if is_speech:
            self._speech_run += 1
            if self._speech_run >= self.min_speech_frames:
                self._has_spoken = True
                self._idle_silence_run = 0
                self._silence_run = 0
                self._segment_fired = False
                return SPEECH
            return SPEECH

        self._speech_run = 0

        # Before the candidate says anything, use a distinct two-stage timer.
        # The normal utterance timer only applies after actual speech starts.
        if not self._has_spoken:
            self._idle_silence_run += 1
            if (
                not self._idle_prompt_sent
                and self._idle_silence_run >= self.prompt_timeout_frames
            ):
                self._idle_prompt_sent = True
                return PROMPT_TIMEOUT
            if self._idle_silence_run >= self.idle_timeout_frames:
                self.reset()
                return IDLE_TIMEOUT
            return SPEECH

        if self._has_spoken:
            self._silence_run += 1

            # Final utterance done (total silence after user finishes answer)
            if self._silence_run >= self.silence_frames_threshold:
                self.reset()
                return UTTERANCE_DONE

            # Prompt timeout (~6s silence)
            if not self._prompt_sent and self._silence_run == self.prompt_timeout_frames:
                self._prompt_sent = True
                return PROMPT_TIMEOUT

            # Start-ahead: safe to pre-generate next question
            if self._silence_run == self.start_ahead_frames_threshold:
                return START_AHEAD

            # Segment done: ~400ms pause -> finalize one live chunk.
            if not self._segment_fired and self._silence_run == self.segment_frames_threshold:
                self._segment_fired = True
                return SEGMENT_DONE

        return SPEECH

    @property
    def has_spoken(self) -> bool:
        return self._has_spoken

    def reset(self):
        self._silence_run = 0
        self._speech_run = 0
        self._has_spoken = False
        self._prompt_sent = False
        self._segment_fired = False
        self._idle_silence_run = 0
        self._idle_prompt_sent = False

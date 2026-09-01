# AI Mock Interview System

Real-time AI voice interview app. Upload a resume + job description, and
the system builds a 12-question interview plan, then conducts it live
over voice: candidate speaks → VAD detects silence → Whisper transcribes →
Mistral generates the next question (streamed) → text is chunked (~150
chars) → each chunk is sent to TTS → audio plays back immediately, so the
AI doesn't wait for a full response before it starts talking.

```
Resume/JD → Parser → Skill Extractor → Interview Planner (12 Qs)
    → Voice loop: VAD → Whisper STT → Mistral (streamed) → Chunker → TTS → playback
```

## Project layout

```
ai-interview-system/
├── backend/                   FastAPI app
│   ├── app/
│   │   ├── main.py            App entrypoint, CORS, router registration
│   │   ├── api/routes/
│   │   │   ├── upload.py      POST /upload/resume, /upload/jd
│   │   │   ├── interview.py   POST /interview/start, /interview/answer
│   │   │   └── voice_ws.py    WS  /interview/voice/{id} — the real-time loop
│   │   ├── services/
│   │   │   ├── resume_parser.py / jd_parser.py   PDF/DOCX text extraction
│   │   │   ├── skill_extractor.py                keyword + LLM-based extraction
│   │   │   ├── interview_planner.py              builds & fills the 12-Q plan
│   │   │   ├── llm_client.py                     Mistral wrapper (complete + stream)
│   │   │   ├── stt_service.py                    Whisper transcription
│   │   │   ├── vad_service.py                    webrtcvad silence detection
│   │   │   ├── text_chunker.py                   streaming ~150-char chunker
│   │   │   └── tts_service.py                    TTS provider adapter (plug in Pocket TTS)
│   │   ├── models/
│   │   │   ├── schemas.py     Pydantic request/response models
│   │   │   └── state.py       In-memory session store (swap for Postgres later)
│   │   └── core/config.py     Settings (env vars)
│   ├── requirements.txt
│   ├── .env.example
│   └── Dockerfile
│
├── frontend/                  React + Vite app
│   ├── src/
│   │   ├── App.jsx                        top-level state/flow
│   │   ├── components/
│   │   │   ├── UploadForm.jsx             resume/JD upload → starts interview
│   │   │   ├── InterviewChat.jsx          transcript bubbles + progress
│   │   │   └── VoiceRecorder.jsx          mic start/stop controls
│   │   ├── hooks/useVoiceInterview.js     mic capture, PCM16 framing, WS + playback
│   │   ├── services/api.js                REST calls + WS URL builder
│   │   └── styles/app.css
│   ├── package.json
│   ├── vite.config.js         dev proxy to backend on :8000
│   └── Dockerfile
│
├── docker-compose.yml
└── .gitignore
```

## Running locally (without Docker)

### Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in MISTRAL_API_KEY at minimum
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```
Visit http://localhost:5173.

## Running with Docker
```bash
cp backend/.env.example backend/.env   # fill in your keys first
docker compose up --build
```

## What's wired up vs. what you need to plug in

| Piece | Status |
|---|---|
| Resume/JD upload, parsing, skill extraction | Working (rule-based fallback; swap to `extract_skills_llm`/`extract_projects_llm` in `skill_extractor.py` for higher accuracy) |
| 12-question interview plan generation | Working — deterministic stage skeleton, LLM fills question text per-turn |
| Mistral LLM integration | Working — set `MISTRAL_API_KEY` in `backend/.env`. Falls back to a mock response if unset, so the app still runs end-to-end for UI testing |
| Whisper STT | Working, downloads the model specified by `WHISPER_MODEL` on first use |
| VAD (silence detection) | Working via `webrtcvad`, tunable thresholds in `vad_service.py` |
| Streaming ~150-char chunker | Working, sentence-boundary aware |
| **TTS ("Pocket TTS")** | **Stub only** — `tts_service.py` has a `_pocket_tts()` placeholder that returns empty audio bytes. Wire in your actual Pocket TTS SDK/API call there; the rest of the pipeline (chunking → per-chunk synthesis → streamed playback) is already built around it |
| Frontend mic capture → 16kHz PCM16 → WebSocket | Working |
| Frontend audio chunk playback | Working via Web Audio `decodeAudioData` — adjust decoding if your TTS provider returns raw PCM instead of a container format like WAV/MP3 |
| Persistent storage (Postgres) | Not wired — MVP uses an in-memory `SessionStore` (`app/models/state.py`). Swap it for a SQLAlchemy-backed repository behind the same interface when you need durability/multi-worker support |

## Notes on the voice loop wire protocol

**Utils Notes On the voice loop wire protocol**

The loop is turn-based: the AI speaks a question → the frontend finishes playback and
signals the backend (`audio_end`) → the backend starts "awaiting an answer" and VADs the
user's mic → after **2 seconds of silence** (`STT_SILENCE_SECONDS`) the answer is committed →
the (pre-generated) next question is spoken straight away → repeat. The backend
**drops any user audio** while it is not awaiting an answer, so the AI's own TTS echo from
the speakers can never be transcribed as an empty user answer (this fixed the runaway loop
of AI always talking).

All 12 questions are generated up-front, in parallel, when the interview starts
(`generate_all_question_texts` in `interview_planner.py`), so there is **no LLM call during
the live conversation** and the next question is available instantly the moment the answer
is committed. Each question is kept short (≤ `QUESTION_WORD_LIMIT` words) for natural speech.

**Client → Server** (over `WS /interview/voice/{interview_id}`):
- Binary frames: raw 16kHz mono PCM16 audio while the candidate is speaking (meaningful
  only while the backend is awaiting an answer)
- `{"type": "audio_end"}`: AI playback finished → backend starts accepting user audio
- `{"type": "end_of_answer"}`: manual flush trigger (used on "Stop & Send Answer")

**Server → Client:**
- `{"type": "partial_transcript", "seq": N, "text": "..."}` — a live, chunk-based STT block. Emitted as soon as a short pause finalizes a speech chunk, so the candidate sees their words appear in real time while they speak. Each chunk is its own block; the frontend appends them in `seq` order.
- `{"type": "transcript", "role": "candidate", "text": "..."}` — the finalized answer (all `partial_transcript` chunks joined), sent after a long silence or `end_of_answer`.
- For each TTS chunk (sent together, in `seq` order, so text is revealed exactly when its audio speaks):
  - `{"type": "ai_text", "seq": N, "text": "..."}` — that chunk's live text
  - `{"type": "audio_chunk", "seq": N, "text": "..."}` immediately followed by a binary frame with that chunk's synthesized audio (chunk → TTS → reveal text + send audio → next chunk, so text and audio stay in sync)
- `{"type": "ai_response", "text": "..."}` — the complete question, sent once all audio is delivered; the frontend shows this as the finalized AI bubble
- `{"type": "question_complete"}` — sentinel: audio + `ai_text` all delivered; when the audio queue drains, the frontend sends `audio_end` and auto-opens the mic
- `{"type": "listening"}` — the answer was empty (nothing transcribed), so the backend keeps the current question and re-opens the mic for the user to try again
- `{"type": "interview_complete"}`

**Live STT tuning** (real-time display + connection stability):
- `STT_SEGMENT_SECONDS` (default `0.5`): the short pause (seconds) that finalizes a live-STT chunk while the candidate keeps talking. Kept at ~500ms so natural micro-pauses don't flush tiny chunks; each flushed chunk has its trailing silence trimmed before transcription to avoid Whisper hallucinating filler ("thank you", "bye", "you").
- `STT_MAX_CHUNK_SECONDS` (default `4.0`): each Whisper transcription is capped to this much audio, so the candidate's words stream to the screen in real time instead of one slow, huge transcription at the end.
- `STT_MAX_CONCURRENCY` (default `2`): bounds how many Whisper calls run at once. Whisper `base` on CPU is slow; unbounded parallelism saturated the CPU, starved the WebSocket keepalive pings and dropped the connection on long answers.
- Whisper is resilient per-slice: sub-second audio (VAD noise/click at a chunk boundary) is skipped, and a `RuntimeError` on a degenerate slice is logged and treated as empty rather than killing the interview.
- Live STT is streamed to the client in strict `seq` order: Whisper tasks finish out of order, so the backend buffers completed chunks and drains them chronologically (the frontend also re-sorts by `seq` as a safety net), keeping the visible live transcript in order.
- When building the final answer, consecutive identical live chunks are collapsed and isolated Whisper hallucination filler phrases ("thank you", "thank you for watching", "bye", standalone "you", "ok", "so") are dropped — but only when a chunk's entire text is such a filler, so genuine words inside real phrases are preserved.

## Extending

- **Add RAG**: only worth it once the resume/JD corpus grows past what fits in a prompt; the design doc explicitly recommends skipping it for the MVP.
- **Swap in Postgres**: implement the same methods as `SessionStore` (`app/models/state.py`) against SQLAlchemy models, then swap the import in the route files.
- **Auth**: none is wired up — add it in front of the `/upload` and `/interview` routers before deploying anywhere multi-tenant.

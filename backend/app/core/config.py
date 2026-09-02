from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    cors_origins: str = "http://localhost:5173"

    mistral_api_key: str = ""
    mistral_model: str = "mistral-small-latest"

    tts_provider: str = "pocket"
    tts_api_key: str = ""
    hf_token: str = ""
    tts_chunk_char_limit: int = 150
    tts_chunk_min_chars: int = 40  # emit the first chunk as soon as text >= this (so playback starts sooner)
    tts_voice: str = "alba"  # any name from the pocket-tts voice catalog, or a local .wav path for cloning

    whisper_model: str = "base"

    # VAD: the short pause (in seconds) that finalizes one live-STT speech chunk
    # while the candidate keeps talking, vs. the trailing silence that ends the whole
    # answer (the "they're done" trigger, after which we move to the next question).
    stt_segment_seconds: float = 0.4  # ~400ms short pause -> finalize one live chunk
    stt_silence_seconds: float = 2.5  # 2.5s trailing silence -> commit answer & move on
    stt_prompt_timeout_seconds: float = 6.0  # 6s with no answer -> reassuring prompt
    stt_no_answer_timeout_seconds: float = 12.0  # 6s more after the 6s prompt -> next question
    # Cap the length of audio given to Whisper per transcription. Long, unfiltered
    # speech can accumulate into huge buffers (tens of seconds); splitting them
    # into small pieces keeps live STT streaming in real time instead of one
    # slow, late transcription at the end.
    stt_max_chunk_seconds: float = 1.5
    # Max concurrent Whisper transcriptions. Increased to 4 so multiple chunks
    # can transcribe in parallel instead of queuing behind each other.
    stt_max_concurrency: int = 4

    database_url: str = "sqlite+aiosqlite:///./interview.db"
    upload_dir: str = "./uploads"

    total_questions: int = 0  # dynamic: based on JD skills count + intro + projects + closing
    project_questions: int = 2  # always ask 2 project questions from resume
    # Max length (words) for each interview question. Keeps questions short and
    # natural for spoken delivery.
    question_word_limit: int = 18

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)

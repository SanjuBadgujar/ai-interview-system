from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    cors_origins: str = "http://localhost:5173"

    # Deepgram STT
    deepgram_api_key: str = ""
    deepgram_api_keys: str = ""
    deepgram_model: str = "nova-2"

    # ElevenLabs TTS
    elevenlabs_api_key: str = ""
    elevenlabs_api_keys: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_model: str = "eleven_multilingual_v2"
    elevenlabs_output_format: str = "pcm_16000"

    # Legacy (kept for compatibility)
    mistral_api_key: str = ""
    mistral_model: str = "mistral-small-latest"

    tts_provider: str = "elevenlabs"
    tts_api_key: str = ""
    hf_token: str = ""
    tts_chunk_char_limit: int = 150
    tts_chunk_min_chars: int = 40
    tts_voice: str = "alba"

    whisper_model: str = "base"

    stt_segment_seconds: float = 0.4
    stt_silence_seconds: float = 2.5
    stt_prompt_timeout_seconds: float = 6.0
    stt_no_answer_timeout_seconds: float = 12.0
    stt_max_chunk_seconds: float = 1.5
    stt_max_concurrency: int = 4

    database_url: str = "sqlite+aiosqlite:///./interview.db"
    upload_dir: str = "./uploads"

    total_questions: int = 0
    project_questions: int = 2
    question_word_limit: int = 18

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)

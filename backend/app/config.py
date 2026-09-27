from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = "http://localhost:8000"
    supabase_service_role_key: str = "replace-me"
    openai_api_key: str = "replace-me"
    openai_segmentation_model: str = "gpt-4o-mini"
    openai_tts_model: str = "tts-1"
    openai_tts_voice: str = "alloy"
    audiobooks_bucket: str = "audiobooks"
    max_tts_chunk_chars: int = 4000
    front_matter_min_pages: int = 15
    front_matter_max_pages: int = 25


settings = Settings()

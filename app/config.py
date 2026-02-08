from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "sel-flection"
    app_env: str = "dev"
    app_secret_key: str = Field(default="change-me-in-prod")
    app_access_token_expire_minutes: int = 60 * 24 * 7
    auth_mode: str = "local"  # local | google
    enable_google_sheets: bool = False

    database_url: str = "sqlite:///./sel_flection.db"

    google_client_id: str = ""
    google_client_secret: str = ""
    google_oauth_token_url: str = "https://oauth2.googleapis.com/token"
    google_userinfo_url: str = "https://www.googleapis.com/oauth2/v3/userinfo"
    google_scopes: str = (
        "openid email profile "
        "https://www.googleapis.com/auth/spreadsheets "
        "https://www.googleapis.com/auth/drive.file"
    )

    token_encryption_key: str = ""

    ai_provider: str = "ollama"  # ollama | gemini | heuristic
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b-instruct"


settings = Settings()

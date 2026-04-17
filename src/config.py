from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # WhatsApp Business Cloud API
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = "default_verify_token"
    whatsapp_api_version: str = "v21.0"

    # OpenRouter
    openrouter_api_key: str = ""
    openrouter_model: str = "anthropic/claude-opus-4"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # GCP
    gcp_project_id: str = ""
    gcs_bucket_name: str = ""
    firestore_collection: str = "conversations"

    # Application
    log_level: str = "INFO"
    conversation_ttl_hours: int = 24
    max_conversation_turns: int = 20
    max_tool_iterations: int = 10

    @property
    def whatsapp_api_base(self) -> str:
        return f"https://graph.facebook.com/{self.whatsapp_api_version}"


settings = Settings()

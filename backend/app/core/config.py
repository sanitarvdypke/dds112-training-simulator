from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_env: str = "local"
    secret_key: str = "change-me"
    database_url: str = "postgresql+asyncpg://dds112:dds112@localhost:5432/dds112"
    cors_origins: str = "http://localhost:5173"
    ai_provider: str = "mock"
    ai_enabled: bool = True
    call_provider: str = "mock"
    rtu_provider: str = "mock"
    jwt_expire_minutes: int = 480
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

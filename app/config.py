from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    RABBITMQ_URL: str = "amqp://admin:localdev@localhost:5672/"
    SERVICE_NAME: str = "progress-service"
    SERVICE_PORT: int = 8003

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

@lru_cache()
def get_settings():
    return Settings()

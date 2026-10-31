from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "AndYouChat"
    env: str = "dev"
    api_prefix: str = "/api/v1"

    database_url: str = "sqlite+aiosqlite:///./andyou.db"
    redis_url: str = "redis://127.0.0.1:6379/0"
    use_fakeredis: bool = False

    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl: int = 60 * 60 * 24 * 7
    refresh_token_ttl: int = 60 * 60 * 24 * 30

    cors_origins: str = "*"
    snowflake_node_id: int = 1
    message_recall_seconds: int = 120
    bcrypt_rounds: int = 12

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

from pydantic import AnyHttpUrl, Field, PostgresDsn, RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: PostgresDsn
    redis_url: RedisDsn
    s3_endpoint: AnyHttpUrl
    s3_access_key: SecretStr
    s3_secret_key: SecretStr
    s3_bucket: str = Field(min_length=1)
    auth_session_ttl_seconds: int = Field(default=30 * 24 * 60 * 60, gt=0)


def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]

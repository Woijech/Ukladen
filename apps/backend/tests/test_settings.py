import pytest
from pydantic import ValidationError
from test_auth_sessions import settings as settings

from app.core.config import Settings


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("s3_access_key", ""),
        ("s3_secret_key", ""),
        ("database_url", "postgresql://test:test@localhost/test"),
        ("database_url", "postgresql+asyncpg://test:test@localhost/test"),
        ("database_url", "postgresql+psycopg2://test:test@localhost/test"),
    ],
)
def test_invalid_connections_fail_during_configuration(
    settings: Settings, field: str, value: str
) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(settings.model_dump() | {field: value})


def test_connection_credentials_are_hidden_in_settings_repr(settings: Settings) -> None:
    config = Settings.model_validate(
        settings.model_dump()
        | {
            "database_url": "postgresql+psycopg://test:private-db-password@localhost/test",
            "redis_url": "redis://:private-redis-password@localhost:6379/0",
            "s3_access_key": "private-storage-key",
            "s3_secret_key": "private-storage-secret",
        }
    )
    assert "private-" not in repr(config)
    assert "private-db-password" in str(config.database_url)
    assert config.s3_secret_key.get_secret_value() == "private-storage-secret"

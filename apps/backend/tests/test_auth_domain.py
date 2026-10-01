from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.modules.auth.domain.entities import AuthSession, OneTimeToken, TokenType
from app.modules.auth.domain.errors import InvalidOneTimeToken, InvalidSession

CREATED_AT = datetime(2026, 10, 1, tzinfo=UTC)
EXPIRES_AT = CREATED_AT + timedelta(days=30)
TOKEN_HASH = "a" * 64


def test_session_validity() -> None:
    session = AuthSession(
        id=uuid4(),
        user_id=uuid4(),
        token_hash=TOKEN_HASH,
        created_at=CREATED_AT,
        last_seen_at=CREATED_AT,
        expires_at=EXPIRES_AT,
    )
    session.require_active(CREATED_AT)
    session.require_active(EXPIRES_AT - timedelta(microseconds=1))
    session.require_active(CREATED_AT.astimezone(timezone(timedelta(hours=3))))
    for now in (CREATED_AT - timedelta(microseconds=1), EXPIRES_AT, EXPIRES_AT + timedelta(1)):
        with pytest.raises(InvalidSession):
            session.require_active(now)
    with pytest.raises(InvalidSession):
        replace(session, revoked_at=CREATED_AT).require_active(CREATED_AT)
    with pytest.raises(ValueError, match="timezone-aware"):
        session.require_active(CREATED_AT.replace(tzinfo=None))
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(session, expires_at=EXPIRES_AT.replace(tzinfo=None))
    assert TOKEN_HASH not in repr(session)


@pytest.mark.parametrize("token_type", list(TokenType))
def test_one_time_token_validity_and_consumption(token_type: TokenType) -> None:
    token = OneTimeToken(
        id=uuid4(),
        user_id=uuid4(),
        token_type=token_type,
        token_hash=TOKEN_HASH,
        created_at=CREATED_AT,
        expires_at=EXPIRES_AT,
    )
    token.require_usable(CREATED_AT)
    token.require_usable(EXPIRES_AT - timedelta(microseconds=1))
    for now in (CREATED_AT - timedelta(microseconds=1), EXPIRES_AT, EXPIRES_AT + timedelta(1)):
        with pytest.raises(InvalidOneTimeToken):
            token.consume(now)
        assert token.used_at is None
    with pytest.raises(ValueError, match="timezone-aware"):
        token.consume(CREATED_AT.replace(tzinfo=None))
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(token, used_at=CREATED_AT.replace(tzinfo=None))
    token.consume(CREATED_AT)
    assert token.used_at == CREATED_AT
    with pytest.raises(InvalidOneTimeToken):
        token.consume(CREATED_AT)
    with pytest.raises(InvalidOneTimeToken):
        token.require_usable(CREATED_AT)
    assert TOKEN_HASH not in repr(token)

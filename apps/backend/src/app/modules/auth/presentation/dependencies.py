import re
from collections.abc import Iterator
from hmac import compare_digest
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Annotated, TypeGuard

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.application.login import LoginService
from app.modules.auth.application.ports import RateLimiter
from app.modules.auth.application.service import SessionService
from app.modules.auth.domain.entities import AuthSession
from app.modules.auth.domain.errors import InvalidSession
from app.modules.auth.infrastructure.repository import (
    SqlAlchemyCredentialRepository,
    SqlAlchemySessionRepository,
)
from app.modules.auth.infrastructure.session_cache import RedisSessionCache
from app.modules.auth.infrastructure.token_service import generate_token, hash_token
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication


def get_config(request: Request) -> Settings:
    return request.app.state.settings


def get_database(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as database:
        yield database


Config = Annotated[Settings, Depends(get_config)]
Database = Annotated[Session, Depends(get_database)]


def get_sessions(request: Request, database: Database, settings: Config) -> SessionService:
    return SessionService(
        SqlAlchemySessionRepository(database),
        RedisSessionCache(request.app.state.redis),
        settings,
        generate_token=generate_token,
        hash_token=hash_token,
    )


Sessions = Annotated[SessionService, Depends(get_sessions)]


def get_login(request: Request, database: Database, sessions: Sessions) -> LoginService:
    return LoginService(
        SqlAlchemyUserAuthentication(database),
        SqlAlchemyCredentialRepository(database),
        request.app.state.passwords,
        sessions,
        dummy_password_hash=request.app.state.dummy_password_hash,
    )


def is_token(value: str | None) -> TypeGuard[str]:
    return value is not None and re.fullmatch(r"[A-Za-z0-9_-]{43}", value) is not None


def require_csrf(request: Request, settings: Config) -> None:
    origins = {str(origin).rstrip("/") for origin in settings.auth_allowed_origins}
    cookie = request.cookies.get(settings.auth_csrf_cookie_name)
    header = request.headers.get("x-csrf-token")
    if request.headers.get("origin") not in origins or not is_token(cookie) or not is_token(header):
        raise HTTPException(403, "CSRF validation failed.")
    if not compare_digest(cookie, header):
        raise HTTPException(403, "CSRF validation failed.")


def get_rate_limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter


def limit_login(
    request: Request, settings: Config, limiter: Annotated[RateLimiter, Depends(get_rate_limiter)]
) -> None:
    peer = request.client.host if request.client else "unknown"
    allowed, retry_after = limiter.check(
        f"login:{hash_token(peer)}",
        settings.auth_login_rate_limit,
        settings.auth_login_rate_window_seconds,
    )
    if not allowed:
        raise HTTPException(
            429, "Too many login attempts.", headers={"Retry-After": str(retry_after)}
        )


def get_current_session(
    request: Request, database: Database, sessions: Sessions, settings: Config
) -> AuthSession:
    token = request.cookies.get(settings.auth_session_cookie_name)
    if token is None:
        raise InvalidSession("Invalid or expired session.")
    with database.begin():
        session = sessions.validate(token)
        if not SqlAlchemyUserAuthentication(database).is_active(session.user_id):
            raise InvalidSession("Invalid or expired session.")
    return session


CurrentSession = Annotated[AuthSession, Depends(get_current_session)]


def client_ip(request: Request) -> IPv4Address | IPv6Address | None:
    try:
        return ip_address(request.client.host) if request.client else None
    except ValueError:
        return None

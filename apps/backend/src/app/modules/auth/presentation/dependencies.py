import re
from collections.abc import Iterator
from hmac import compare_digest
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Annotated, TypeGuard

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.application.login import LoginService
from app.modules.auth.application.password_recovery import PasswordRecoveryService
from app.modules.auth.application.ports import EmailDeliveryUnavailable, EmailSender, RateLimiter
from app.modules.auth.application.registration import RegistrationService
from app.modules.auth.application.service import SessionService
from app.modules.auth.application.verification import EmailVerificationService
from app.modules.auth.domain.entities import AuthSession
from app.modules.auth.domain.errors import InvalidSession
from app.modules.auth.infrastructure.repository import (
    SqlAlchemyCredentialRepository,
    SqlAlchemyEmailVerificationRepository,
    SqlAlchemyPasswordResetRepository,
    SqlAlchemyRegistrationRepository,
    SqlAlchemySessionRepository,
)
from app.modules.auth.infrastructure.session_cache import RedisSessionCache
from app.modules.auth.infrastructure.token_service import generate_token, hash_token
from app.modules.users.infrastructure.repository import (
    SqlAlchemyEmailVerifier,
    SqlAlchemyUserAuthentication,
    SqlAlchemyUserRegistration,
)


def get_config(request: Request) -> Settings:
    return request.app.state.settings


def get_database(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as database:
        yield database


Config = Annotated[Settings, Depends(get_config)]
Database = Annotated[Session, Depends(get_database)]


def get_email_sender(request: Request, settings: Config) -> EmailSender:
    if settings.auth_email_delivery_mode == "disabled":
        raise EmailDeliveryUnavailable("Email delivery is unavailable.")
    return request.app.state.email_sender


def get_sessions(request: Request, database: Database, settings: Config) -> SessionService:
    return SessionService(
        SqlAlchemySessionRepository(database),
        RedisSessionCache(request.app.state.redis),
        settings,
        generate_token=generate_token,
        hash_token=hash_token,
    )


Sessions = Annotated[SessionService, Depends(get_sessions)]


def get_registration(
    request: Request, database: Database, sessions: Sessions, settings: Config
) -> RegistrationService:
    return RegistrationService(
        SqlAlchemyUserRegistration(database),
        SqlAlchemyRegistrationRepository(database),
        request.app.state.passwords,
        sessions,
        settings,
        generate_token=generate_token,
        hash_token=hash_token,
    )


def get_login(request: Request, database: Database, sessions: Sessions) -> LoginService:
    return LoginService(
        SqlAlchemyUserAuthentication(database),
        SqlAlchemyCredentialRepository(database),
        request.app.state.passwords,
        sessions,
        dummy_password_hash=request.app.state.dummy_password_hash,
    )


def get_password_recovery(
    request: Request, database: Database, sessions: Sessions, settings: Config
) -> PasswordRecoveryService:
    return PasswordRecoveryService(
        SqlAlchemyUserAuthentication(database),
        SqlAlchemyCredentialRepository(database),
        SqlAlchemyPasswordResetRepository(database),
        request.app.state.passwords,
        sessions,
        settings,
        generate_token=generate_token,
        hash_token=hash_token,
    )


def get_email_verification(database: Database) -> EmailVerificationService:
    return EmailVerificationService(
        SqlAlchemyEmailVerificationRepository(database),
        SqlAlchemyEmailVerifier(database),
        hash_token=hash_token,
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


def limit_registration(
    request: Request, settings: Config, limiter: Annotated[RateLimiter, Depends(get_rate_limiter)]
) -> None:
    peer = request.client.host if request.client else "unknown"
    allowed, retry_after = limiter.check(
        f"register:{hash_token(peer)}",
        settings.auth_register_rate_limit,
        settings.auth_register_rate_window_seconds,
    )
    if not allowed:
        raise HTTPException(
            429,
            "Too many registration attempts.",
            headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
        )


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


def limit_email_verification_confirm(
    request: Request, settings: Config, limiter: Annotated[RateLimiter, Depends(get_rate_limiter)]
) -> None:
    peer = request.client.host if request.client else "unknown"
    allowed, retry_after = limiter.check(
        f"email-verification-confirm:{hash_token(peer)}",
        settings.auth_email_verification_confirm_rate_limit,
        settings.auth_email_verification_confirm_rate_window_seconds,
    )
    if not allowed:
        raise HTTPException(
            429,
            "Too many email verification attempts.",
            headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
        )


def limit_password_reset_confirm(
    request: Request, settings: Config, limiter: Annotated[RateLimiter, Depends(get_rate_limiter)]
) -> None:
    peer = request.client.host if request.client else "unknown"
    allowed, retry_after = limiter.check(
        f"password-reset-confirm:{hash_token(peer)}",
        settings.auth_password_reset_confirm_rate_limit,
        settings.auth_password_reset_confirm_rate_window_seconds,
    )
    if not allowed:
        raise HTTPException(
            429,
            "Too many password reset attempts.",
            headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
        )


def limit_password_reset_request(
    request: Request, settings: Config, limiter: Annotated[RateLimiter, Depends(get_rate_limiter)]
) -> None:
    peer = request.client.host if request.client else "unknown"
    allowed, retry_after = limiter.check(
        f"password-reset-request:{hash_token(peer)}",
        settings.auth_password_reset_request_rate_limit,
        settings.auth_password_reset_request_rate_window_seconds,
    )
    if not allowed:
        raise HTTPException(
            429,
            "Too many password reset requests.",
            headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
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


def limit_password_change(
    current: CurrentSession,
    settings: Config,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> None:
    allowed, retry_after = limiter.check(
        f"password-change:{current.user_id}",
        settings.auth_password_change_rate_limit,
        settings.auth_password_change_rate_window_seconds,
    )
    if not allowed:
        raise HTTPException(
            429,
            "Too many password change attempts.",
            headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
        )


def client_ip(request: Request) -> IPv4Address | IPv6Address | None:
    try:
        return ip_address(request.client.host) if request.client else None
    except ValueError:
        return None

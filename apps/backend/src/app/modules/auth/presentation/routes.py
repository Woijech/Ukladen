from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.modules.auth.application.login import LoginService
from app.modules.auth.application.password_recovery import PasswordRecoveryService
from app.modules.auth.application.ports import RateLimiterUnavailable, SessionCacheUnavailable
from app.modules.auth.domain.errors import (
    InvalidCredentials,
    InvalidPassword,
    InvalidSession,
    SessionNotFound,
)
from app.modules.auth.infrastructure.token_service import generate_token
from app.modules.auth.presentation.dependencies import (
    Config,
    CurrentSession,
    Database,
    Sessions,
    client_ip,
    get_login,
    get_password_recovery,
    is_token,
    limit_login,
    limit_password_change,
    require_csrf,
)
from app.modules.auth.presentation.schemas import (
    CsrfResponse,
    LoginRequest,
    LoginResponse,
    PasswordChangeRequest,
    SessionResponse,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def clear_session_cookie(response: Response, settings: Config) -> None:
    response.delete_cookie(
        settings.auth_session_cookie_name,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite=settings.auth_cookie_samesite,
    )


@router.get("/csrf", response_model=CsrfResponse)
def csrf(request: Request, response: Response, settings: Config) -> CsrfResponse:
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "CSRF validation failed.")
    token = request.cookies.get(settings.auth_csrf_cookie_name)
    if not is_token(token):
        token = generate_token()
    response.set_cookie(
        settings.auth_csrf_cookie_name,
        token,
        max_age=settings.auth_session_ttl_seconds,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite=settings.auth_cookie_samesite,
    )
    response.headers["Cache-Control"] = "no-store"
    return CsrfResponse(csrf_token=token)


@router.post(
    "/login",
    response_model=LoginResponse,
    dependencies=[Depends(require_csrf), Depends(limit_login)],
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    settings: Config,
    database: Database,
    service: Annotated[LoginService, Depends(get_login)],
) -> LoginResponse:
    with database.begin():
        issued = service.login(
            payload.email,
            payload.password.get_secret_value(),
            user_agent=request.headers.get("user-agent", "")[:1024] or None,
            ip_address=client_ip(request),
        )
    response.set_cookie(
        settings.auth_session_cookie_name,
        issued.token,
        max_age=settings.auth_session_ttl_seconds,
        expires=issued.session.expires_at,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite=settings.auth_cookie_samesite,
    )
    response.headers["Cache-Control"] = "no-store"
    return LoginResponse(
        user_id=issued.session.user_id,
        session_id=issued.session.id,
        expires_at=issued.session.expires_at,
    )


@router.post("/logout", status_code=204, dependencies=[Depends(require_csrf)])
def logout(
    current: CurrentSession, database: Database, sessions: Sessions, settings: Config
) -> Response:
    with database.begin():
        sessions.revoke(current.id)
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    clear_session_cookie(response, settings)
    return response


@router.post("/logout-all", status_code=204, dependencies=[Depends(require_csrf)])
def logout_all(
    current: CurrentSession, database: Database, sessions: Sessions, settings: Config
) -> Response:
    with database.begin():
        sessions.revoke_all_for_user(current.user_id)
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    clear_session_cookie(response, settings)
    return response


@router.get("/sessions", response_model=list[SessionResponse])
def list_sessions(
    current: CurrentSession, database: Database, sessions: Sessions, response: Response
) -> list[SessionResponse]:
    with database.begin():
        active = sessions.list_active_for_user(current.user_id)
    response.headers["Cache-Control"] = "no-store"
    return [
        SessionResponse(
            id=session.id,
            created_at=session.created_at,
            last_seen_at=session.last_seen_at,
            expires_at=session.expires_at,
            user_agent=session.user_agent,
            ip_address=session.ip_address,
            is_current=session.id == current.id,
        )
        for session in active
    ]


@router.delete("/sessions/{session_id}", status_code=204, dependencies=[Depends(require_csrf)])
def revoke_session(
    session_id: UUID,
    current: CurrentSession,
    database: Database,
    sessions: Sessions,
    settings: Config,
) -> Response:
    with database.begin():
        sessions.revoke_for_user(session_id, current.user_id)
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    if session_id == current.id:
        clear_session_cookie(response, settings)
    return response


@router.post(
    "/password/change",
    status_code=204,
    dependencies=[Depends(require_csrf), Depends(limit_password_change)],
)
def change_password(
    payload: PasswordChangeRequest,
    current: CurrentSession,
    database: Database,
    service: Annotated[PasswordRecoveryService, Depends(get_password_recovery)],
) -> Response:
    try:
        with database.begin():
            service.change_password(
                current.user_id,
                current.id,
                payload.current_password.get_secret_value(),
                payload.new_password.get_secret_value(),
            )
    except InvalidCredentials:
        raise HTTPException(
            401, "Invalid current password.", headers={"Cache-Control": "no-store"}
        ) from None
    except InvalidPassword:
        raise HTTPException(
            400,
            "New password does not meet the password policy.",
            headers={"Cache-Control": "no-store"},
        ) from None
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


def install_auth(application: FastAPI) -> None:
    def invalid_request(request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(
            {"detail": "Invalid request."}, status_code=422, headers={"Cache-Control": "no-store"}
        )

    def invalid_credentials(request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(
            {"detail": "Invalid email or password."},
            status_code=401,
            headers={"Cache-Control": "no-store"},
        )

    def invalid_session(request: Request, error: Exception) -> JSONResponse:
        response = JSONResponse(
            {"detail": "Invalid or expired session."},
            status_code=401,
            headers={"Cache-Control": "no-store"},
        )
        clear_session_cookie(response, request.app.state.settings)
        return response

    def unavailable(request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(
            {"detail": "Service unavailable."},
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )

    def session_not_found(request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(
            {"detail": "Session not found."},
            status_code=404,
            headers={"Cache-Control": "no-store"},
        )

    application.add_exception_handler(RequestValidationError, invalid_request)
    application.add_exception_handler(InvalidCredentials, invalid_credentials)
    application.add_exception_handler(InvalidSession, invalid_session)
    application.add_exception_handler(SessionNotFound, session_not_found)
    for error_type in (SQLAlchemyError, SessionCacheUnavailable, RateLimiterUnavailable):
        application.add_exception_handler(error_type, unavailable)
    application.include_router(router)

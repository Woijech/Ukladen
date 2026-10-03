import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.modules.auth.application.dto import IssuedSession
from app.modules.auth.application.login import LoginService
from app.modules.auth.application.password_recovery import PasswordRecoveryService
from app.modules.auth.application.ports import (
    EmailDeliveryUnavailable,
    EmailSender,
    RateLimiterUnavailable,
    SessionCacheUnavailable,
)
from app.modules.auth.application.registration import RegistrationService
from app.modules.auth.application.verification import EmailVerificationService
from app.modules.auth.application.verification_request import EmailVerificationRequestService
from app.modules.auth.domain.errors import (
    InvalidCredentials,
    InvalidOneTimeToken,
    InvalidPassword,
    InvalidRegistration,
    InvalidSession,
    RegistrationConflict,
    SessionNotFound,
)
from app.modules.auth.infrastructure.token_service import generate_token
from app.modules.auth.presentation.dependencies import (
    Config,
    CurrentSession,
    Database,
    Sessions,
    client_ip,
    get_email_sender,
    get_email_verification,
    get_email_verification_request,
    get_login,
    get_password_recovery,
    get_registration,
    is_token,
    limit_email_verification_confirm,
    limit_email_verification_request,
    limit_login,
    limit_password_change,
    limit_password_reset_confirm,
    limit_password_reset_request,
    limit_registration,
    require_csrf,
)
from app.modules.auth.presentation.schemas import (
    CsrfResponse,
    EmailVerificationRequest,
    EmailVerificationRequestResponse,
    EmailVerificationResendRequest,
    LoginRequest,
    LoginResponse,
    PasswordChangeRequest,
    PasswordResetConfirmationRequest,
    PasswordResetRequest,
    PasswordResetRequestResponse,
    RegistrationRequest,
    SessionResponse,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
logger = logging.getLogger(__name__)


def set_session_cookie(response: Response, issued: IssuedSession, settings: Config) -> None:
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
    set_session_cookie(response, issued, settings)
    response.headers["Cache-Control"] = "no-store"
    return LoginResponse(
        user_id=issued.session.user_id,
        session_id=issued.session.id,
        expires_at=issued.session.expires_at,
    )


@router.post(
    "/register",
    status_code=201,
    response_model=LoginResponse,
    dependencies=[Depends(require_csrf), Depends(limit_registration)],
)
def register(
    payload: RegistrationRequest,
    request: Request,
    response: Response,
    settings: Config,
    database: Database,
    sender: Annotated[EmailSender, Depends(get_email_sender)],
    service: Annotated[RegistrationService, Depends(get_registration)],
) -> LoginResponse:
    try:
        with database.begin():
            result = service.register(
                payload.email,
                payload.password.get_secret_value(),
                user_agent=request.headers.get("user-agent", "")[:1024] or None,
                ip_address=client_ip(request),
            )
    except InvalidRegistration:
        raise HTTPException(
            400, "Invalid registration input.", headers={"Cache-Control": "no-store"}
        ) from None
    except RegistrationConflict:
        raise HTTPException(
            409, "Registration could not be completed.", headers={"Cache-Control": "no-store"}
        ) from None
    set_session_cookie(response, result.session, settings)
    try:
        sender.send_email_verification(result.email, result.verification_token)
    except EmailDeliveryUnavailable:
        # ponytail: publication after commit can lose mail; add an outbox for durable delivery.
        logger.warning(
            "Registration email queue failed.",
            extra={"user_id": str(result.user_id), "event": "auth.registration.email_queue_failed"},
        )
    response.headers["Cache-Control"] = "no-store"
    return LoginResponse(
        user_id=result.user_id,
        session_id=result.session.session.id,
        expires_at=result.session.session.expires_at,
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


@router.post(
    "/email-verification/confirm",
    status_code=204,
    dependencies=[Depends(require_csrf), Depends(limit_email_verification_confirm)],
)
def confirm_email_verification(
    payload: EmailVerificationRequest,
    database: Database,
    service: Annotated[EmailVerificationService, Depends(get_email_verification)],
) -> Response:
    try:
        with database.begin():
            service.confirm(payload.token.get_secret_value())
    except InvalidOneTimeToken:
        raise HTTPException(
            400, "Invalid or expired token.", headers={"Cache-Control": "no-store"}
        ) from None
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post(
    "/email-verification/request",
    status_code=202,
    response_model=EmailVerificationRequestResponse,
    dependencies=[Depends(require_csrf), Depends(limit_email_verification_request)],
)
def request_email_verification(
    payload: EmailVerificationResendRequest,
    current: CurrentSession,
    response: Response,
    database: Database,
    sender: Annotated[EmailSender, Depends(get_email_sender)],
    service: Annotated[EmailVerificationRequestService, Depends(get_email_verification_request)],
) -> EmailVerificationRequestResponse:
    with database.begin():
        delivery = service.request(current.user_id)
    if delivery is not None:
        try:
            sender.send_email_verification(delivery.email, delivery.token)
        except EmailDeliveryUnavailable:
            # ponytail: publication after commit can lose mail; add an outbox for durable delivery.
            logger.warning(
                "Email verification queue failed.",
                extra={
                    "user_id": str(current.user_id),
                    "event": "auth.email_verification.email_queue_failed",
                },
            )
    response.headers["Cache-Control"] = "no-store"
    return EmailVerificationRequestResponse()


@router.post(
    "/password-reset/confirm",
    status_code=204,
    dependencies=[Depends(require_csrf), Depends(limit_password_reset_confirm)],
)
def confirm_password_reset(
    payload: PasswordResetConfirmationRequest,
    database: Database,
    settings: Config,
    service: Annotated[PasswordRecoveryService, Depends(get_password_recovery)],
) -> Response:
    try:
        with database.begin():
            service.confirm_reset(
                payload.token.get_secret_value(), payload.new_password.get_secret_value()
            )
    except InvalidOneTimeToken:
        raise HTTPException(
            400, "Invalid or expired token.", headers={"Cache-Control": "no-store"}
        ) from None
    except InvalidPassword:
        raise HTTPException(
            400,
            "New password does not meet the password policy.",
            headers={"Cache-Control": "no-store"},
        ) from None
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    clear_session_cookie(response, settings)
    return response


@router.post(
    "/password-reset/request",
    status_code=202,
    response_model=PasswordResetRequestResponse,
    dependencies=[Depends(require_csrf), Depends(limit_password_reset_request)],
)
def request_password_reset(
    payload: PasswordResetRequest,
    response: Response,
    database: Database,
    sender: Annotated[EmailSender, Depends(get_email_sender)],
    service: Annotated[PasswordRecoveryService, Depends(get_password_recovery)],
) -> PasswordResetRequestResponse:
    with database.begin():
        delivery = service.request_reset(payload.email)
    if delivery is not None:
        try:
            sender.send_password_reset(delivery.email, delivery.token)
        except EmailDeliveryUnavailable:
            # ponytail: publication after commit can lose mail; add an outbox for durable delivery.
            logger.warning(
                "Password reset email queue failed.",
                extra={
                    "user_id": str(delivery.user_id),
                    "event": "auth.password_reset.email_queue_failed",
                },
            )
    response.headers["Cache-Control"] = "no-store"
    return PasswordResetRequestResponse()


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
    for error_type in (
        SQLAlchemyError,
        SessionCacheUnavailable,
        RateLimiterUnavailable,
        EmailDeliveryUnavailable,
    ):
        application.add_exception_handler(error_type, unavailable)
    application.include_router(router)

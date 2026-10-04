from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from celery import Celery
from fastapi import FastAPI, Request, Response

from app.core.config import Settings, get_settings
from app.core.health import HealthChecks, HealthResponse
from app.db.session import create_database_engine, create_session_factory
from app.modules.auth.infrastructure.email_sender import CeleryEmailSender
from app.modules.auth.infrastructure.google_oidc import GoogleOidcProvider
from app.modules.auth.infrastructure.password_hasher import Argon2PasswordHasher
from app.modules.auth.infrastructure.request_protection import RedisRateLimiter
from app.modules.auth.infrastructure.token_service import generate_token
from app.modules.auth.presentation.routes import install_auth
from app.modules.users.presentation.routes import install_users


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        config = settings or get_settings()
        engine = create_database_engine(config)
        health = HealthChecks(engine, config)
        application.state.health = health
        application.state.session_factory = create_session_factory(engine)
        application.state.settings = config
        application.state.redis = health.redis
        application.state.rate_limiter = RedisRateLimiter(health.redis)
        application.state.passwords = Argon2PasswordHasher()
        application.state.google_provider = (
            GoogleOidcProvider(config, health.http) if config.google_client_id is not None else None
        )
        celery = Celery("ukladen", broker=str(config.redis_url), set_as_current=False)
        try:
            celery.conf.update(
                task_protocol=2,
                task_serializer="json",
                accept_content=["json"],
                task_ignore_result=True,
                broker_connection_timeout=3,
                broker_transport_options={"socket_connect_timeout": 3, "socket_timeout": 3},
            )
            application.state.email_sender = CeleryEmailSender(celery, config)
            application.state.dummy_password_hash = application.state.passwords.hash(
                generate_token()
            )
            yield
        finally:
            celery.close()
            health.close()
            engine.dispose()

    application = FastAPI(
        title="Ukladen",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    install_auth(application)
    install_users(application)

    @application.get("/api/health/live", response_model=HealthResponse)
    def liveness() -> HealthResponse:
        return HealthResponse(status="ok")

    @application.get("/api/health/ready", response_model=HealthResponse)
    def readiness(request: Request, response: Response) -> HealthResponse:
        health: HealthChecks = request.app.state.health
        result = health.readiness()
        if result.status != "ok":
            response.status_code = 503
        return result

    return application


app = create_app()

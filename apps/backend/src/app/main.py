from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from app.core.config import Settings, get_settings
from app.core.health import HealthChecks, HealthResponse
from app.db.session import create_database_engine, create_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        config = settings or get_settings()
        engine = create_database_engine(config)
        health = HealthChecks(engine, config)
        application.state.health = health
        application.state.session_factory = create_session_factory(engine)
        try:
            yield
        finally:
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

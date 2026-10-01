import logging
from typing import Literal

import httpx
from pydantic import BaseModel
from redis import Redis
from sqlalchemy import Engine, text

from app.core.config import Settings

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    checks: dict[str, bool] | None = None


class HealthChecks:
    def __init__(self, engine: Engine, settings: Settings) -> None:
        self.engine = engine
        self.redis = Redis.from_url(
            str(settings.redis_url), socket_connect_timeout=3, socket_timeout=3
        )
        self.http = httpx.Client(base_url=str(settings.s3_endpoint), timeout=3)

    def check_postgres(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(text("SET statement_timeout = '3s'"))
            connection.execute(text("SELECT 1"))

    def check_redis(self) -> None:
        self.redis.ping()

    def check_storage(self) -> None:
        self.http.get("/readyz").raise_for_status()

    def readiness(self) -> HealthResponse:
        checks: dict[str, bool] = {}
        for name, check in (
            ("postgres", self.check_postgres),
            ("redis", self.check_redis),
            ("storage", self.check_storage),
        ):
            try:
                check()
                checks[name] = True
            except Exception:
                logger.warning("Readiness check failed: %s", name)
                checks[name] = False
        return HealthResponse(status="ok" if all(checks.values()) else "unavailable", checks=checks)

    def close(self) -> None:
        self.redis.close()
        self.http.close()

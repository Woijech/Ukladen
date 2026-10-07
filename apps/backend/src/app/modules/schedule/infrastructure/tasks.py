import logging

import httpx

from app.core.config import get_settings
from app.core.logging import log_failure
from app.db.session import create_database_engine, create_session_factory
from app.integrations.bsuir.public_api import IisPublicProvider
from app.modules.academics.infrastructure.repository import SqlAlchemySelectedGroupDirectory
from app.modules.schedule.application.synchronization import (
    ScheduleRefreshService,
    ScheduleSyncService,
    ScheduleSyncUnavailable,
)
from app.modules.schedule.infrastructure.jobs import CeleryScheduleJobs, SyncRequest
from app.modules.schedule.infrastructure.storage import SqlAlchemyScheduleStore
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="schedule.sync_group", ignore_result=True, store_errors_even_if_ignored=False)
def sync_group(**payload: object) -> None:
    try:
        job = SyncRequest.model_validate(payload)
        settings = get_settings()
        if not settings.schedule_sync_enabled:
            return
        engine = create_database_engine(settings)
        try:
            store = SqlAlchemyScheduleStore(
                create_session_factory(engine), settings.schedule_sync_interval_seconds
            )
            with httpx.Client(timeout=5, follow_redirects=False, trust_env=False) as client:
                ScheduleSyncService(IisPublicProvider(client), store).sync(
                    job.group_id, job.group_number, force=job.force
                )
        finally:
            engine.dispose()
    except Exception as error:
        log_failure(logger, "schedule.task_failed", error)
        raise ScheduleSyncUnavailable("Schedule synchronization is unavailable.") from None


@celery_app.task(
    name="schedule.refresh_selected", ignore_result=True, store_errors_even_if_ignored=False
)
def refresh_selected() -> None:
    try:
        settings = get_settings()
        if not settings.schedule_sync_enabled:
            return
        engine = create_database_engine(settings)
        try:
            sessions = create_session_factory(engine)
            store = SqlAlchemyScheduleStore(sessions, settings.schedule_sync_interval_seconds)
            # Read the academic module through its application-owned directory port.
            ScheduleRefreshService(
                SqlAlchemySelectedGroupDirectory(sessions),
                store,
                CeleryScheduleJobs(celery_app),
                settings.schedule_sync_interval_seconds,
            ).refresh()
        finally:
            engine.dispose()
    except Exception as error:
        log_failure(logger, "schedule.task_failed", error)
        raise ScheduleSyncUnavailable("Schedule synchronization is unavailable.") from None

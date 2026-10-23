import logging

from app.core.config import get_settings
from app.core.logging import log_failure
from app.db.session import create_database_engine, create_session_factory
from app.modules.ai.domain.state import AiPersistenceUnavailable
from app.modules.ai.infrastructure.recovery import reconcile_runs
from app.modules.ai.infrastructure.retention import purge_expired
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="ai.reconcile_runs", ignore_result=True, store_errors_even_if_ignored=False)
def reconcile() -> None:
    settings = get_settings()
    if not (settings.ai_enabled or settings.ai_retention_enabled):
        return
    try:
        engine = create_database_engine(settings)
        try:
            sessions = create_session_factory(engine)
            reconcile_runs(sessions)
            purge_expired(sessions)
        finally:
            engine.dispose()
    except Exception as error:
        log_failure(logger, "ai.recovery_failed", error)
        raise AiPersistenceUnavailable("AI recovery is unavailable.") from None

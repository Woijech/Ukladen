from celery import Celery
from pydantic import BaseModel, ConfigDict, Field

from app.modules.schedule.application.synchronization import ScheduleSyncUnavailable


class SyncRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)

    group_id: int = Field(gt=0, le=2**63 - 1)
    group_number: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$")
    force: bool = False


class CeleryScheduleJobs:
    def __init__(self, celery: Celery, *, enabled: bool = True) -> None:
        self.celery, self.enabled = celery, enabled

    def request_sync(self, group_id: int, group_number: str, *, force: bool = False) -> None:
        try:
            if not self.enabled:
                raise ScheduleSyncUnavailable()
            job = SyncRequest(group_id=group_id, group_number=group_number, force=force)
            self.celery.send_task(
                "schedule.sync_group",
                kwargs=job.model_dump(),
                ignore_result=True,
                retry=False,
                expires=120,
            )
        except Exception:
            raise ScheduleSyncUnavailable("Schedule synchronization is unavailable.") from None

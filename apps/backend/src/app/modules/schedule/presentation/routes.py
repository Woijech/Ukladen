import logging
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse

from app.core.logging import log_failure
from app.modules.academics.presentation.routes import Academics, IdentifierPath, no_store
from app.modules.auth.application.ports import RateLimiter
from app.modules.auth.presentation.dependencies import (
    CurrentSession,
    Database,
    get_current_session,
    get_rate_limiter,
    require_csrf,
)
from app.modules.schedule.application.provider import (
    Announcement,
    AnnouncementPage,
    Schedule,
    ScheduleProvider,
    UpdateDate,
)
from app.modules.schedule.application.queries import (
    ScheduleEventNotFound,
    ScheduleQueryService,
    require_profile,
)
from app.modules.schedule.application.schedule import AcademicProfileRequired, ScheduleService
from app.modules.schedule.application.synchronization import ScheduleJobs, ScheduleSyncUnavailable
from app.modules.schedule.domain.events import InvalidScheduleRange
from app.modules.schedule.infrastructure.storage import SqlAlchemyScheduleStore
from app.modules.schedule.presentation.schemas import (
    OfficialEventResponse,
    ScheduleEventsResponse,
    ScheduleStateResponse,
    SyncAcceptedResponse,
)

router = APIRouter(
    prefix="/api/v1/schedule",
    tags=["schedule"],
    dependencies=[Depends(get_current_session), Depends(no_store)],
)
GroupNumberPath = Annotated[str, Path(min_length=1, max_length=200)]
UrlIdPath = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,200}$")]
SubgroupQuery = Annotated[int | None, Query(gt=0, le=2**31 - 1)]


def get_schedule_provider(request: Request) -> ScheduleProvider:
    return request.app.state.schedule_provider


Provider = Annotated[ScheduleProvider, Depends(get_schedule_provider)]


def get_schedule_service(provider: Provider) -> ScheduleService:
    return ScheduleService(provider)


Schedules = Annotated[ScheduleService, Depends(get_schedule_service)]


def get_schedule_queries(request: Request) -> ScheduleQueryService:
    return ScheduleQueryService(
        SqlAlchemyScheduleStore(
            request.app.state.session_factory,
            request.app.state.settings.schedule_sync_interval_seconds,
        )
    )


def get_schedule_jobs(request: Request) -> ScheduleJobs:
    return request.app.state.schedule_jobs


Queries = Annotated[ScheduleQueryService, Depends(get_schedule_queries)]
Jobs = Annotated[ScheduleJobs, Depends(get_schedule_jobs)]


@router.get("/me/events", response_model=ScheduleEventsResponse)
def get_my_events(
    current: CurrentSession,
    database: Database,
    academics: Academics,
    queries: Queries,
    date_from: date,
    date_to: date,
) -> ScheduleEventsResponse:
    with database.begin():
        profile = academics.get(current.user_id)
    return ScheduleEventsResponse.model_validate(queries.for_profile(profile, date_from, date_to))


@router.get("/groups/{group_number}/events", response_model=ScheduleEventsResponse)
def get_group_events(
    group_number: GroupNumberPath,
    queries: Queries,
    date_from: date,
    date_to: date,
    subgroup: SubgroupQuery = None,
) -> ScheduleEventsResponse:
    return ScheduleEventsResponse.model_validate(
        queries.for_group(group_number, date_from, date_to, subgroup)
    )


@router.get("/events/{event_id}", response_model=OfficialEventResponse)
def get_official_event(
    event_id: UUID,
    current: CurrentSession,
    database: Database,
    academics: Academics,
    queries: Queries,
) -> OfficialEventResponse:
    with database.begin():
        profile = academics.get(current.user_id)
    return OfficialEventResponse.model_validate(queries.event(event_id, profile))


@router.get("/me/sync-status", response_model=ScheduleStateResponse)
def get_my_sync_status(
    current: CurrentSession,
    database: Database,
    academics: Academics,
    queries: Queries,
) -> ScheduleStateResponse:
    with database.begin():
        profile = academics.get(current.user_id)
    return ScheduleStateResponse.model_validate(queries.state(profile))


@router.post(
    "/me/sync",
    status_code=202,
    response_model=SyncAcceptedResponse,
    dependencies=[Depends(require_csrf)],
)
def request_my_sync(
    current: CurrentSession,
    database: Database,
    academics: Academics,
    jobs: Jobs,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> SyncAcceptedResponse:
    with database.begin():
        profile = require_profile(academics.get(current.user_id))
    allowed, retry = limiter.check(f"schedule-sync:{profile.group.id}", 1, 60)
    if not allowed:
        raise HTTPException(
            429, "Too many synchronization requests.", headers={"Retry-After": str(retry)}
        )
    jobs.request_sync(profile.group.id, profile.group.name, force=True)
    return SyncAcceptedResponse(group_id=profile.group.id)


@router.get("/me", response_model=Schedule | None)
def get_my_schedule(
    current: CurrentSession, database: Database, academics: Academics, schedules: Schedules
) -> Schedule | None:
    with database.begin():
        profile = academics.get(current.user_id)
    return schedules.for_profile(profile)


@router.get("/groups/{group_number}", response_model=Schedule | None)
def get_group_schedule(
    group_number: GroupNumberPath, schedules: Schedules, subgroup: SubgroupQuery = None
) -> Schedule | None:
    return schedules.for_group(group_number, subgroup)


@router.get("/teachers/{teacher_id}", response_model=Schedule | None)
def get_teacher_schedule(teacher_id: IdentifierPath, provider: Provider) -> Schedule | None:
    return provider.get_teacher_schedule(teacher_id)


@router.get("/teachers/by-url-id/{url_id}", response_model=Schedule | None)
def get_teacher_schedule_by_url_id(url_id: UrlIdPath, provider: Provider) -> Schedule | None:
    return provider.get_teacher_schedule_by_url_id(url_id)


@router.get("/teachers/{teacher_id}/announcements", response_model=AnnouncementPage)
def get_teacher_announcements(
    teacher_id: IdentifierPath,
    provider: Provider,
    page: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    date_from: date | None = None,
) -> AnnouncementPage:
    return provider.get_teacher_announcements(teacher_id, page=page, size=size, date_from=date_from)


@router.get("/teachers/by-url-id/{url_id}/announcements", response_model=AnnouncementPage)
def get_teacher_announcements_by_url_id(
    url_id: UrlIdPath,
    provider: Provider,
    page: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    date_from: date | None = None,
) -> AnnouncementPage:
    return provider.get_teacher_announcements_by_url_id(
        url_id, page=page, size=size, date_from=date_from
    )


@router.get("/departments/{department_id}/announcements", response_model=list[Announcement])
def get_department_announcements(
    department_id: IdentifierPath, provider: Provider
) -> list[Announcement]:
    return provider.get_department_announcements(department_id)


@router.get("/groups/{group_number}/last-update", response_model=UpdateDate)
def get_group_update_date(group_number: GroupNumberPath, provider: Provider) -> UpdateDate:
    return UpdateDate(date=provider.get_group_update_date(group_number=group_number))


@router.get("/groups/by-id/{group_id}/last-update", response_model=UpdateDate)
def get_group_update_date_by_id(group_id: IdentifierPath, provider: Provider) -> UpdateDate:
    return UpdateDate(date=provider.get_group_update_date(group_id=group_id))


@router.get("/teachers/{teacher_id}/last-update", response_model=UpdateDate)
def get_teacher_update_date(teacher_id: IdentifierPath, provider: Provider) -> UpdateDate:
    return UpdateDate(date=provider.get_teacher_update_date(teacher_id=teacher_id))


@router.get("/teachers/by-url-id/{url_id}/last-update", response_model=UpdateDate)
def get_teacher_update_date_by_url_id(url_id: UrlIdPath, provider: Provider) -> UpdateDate:
    return UpdateDate(date=provider.get_teacher_update_date(url_id=url_id))


@router.get("/current-week", response_model=int)
def get_current_week(provider: Provider) -> int:
    return provider.get_current_week()


def install_schedule(application: FastAPI) -> None:
    def missing_profile(request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(
            {"detail": "Select an academic group first."},
            status_code=409,
            headers={"Cache-Control": "no-store"},
        )

    def schedule_error(request: Request, error: Exception) -> JSONResponse:
        if isinstance(error, InvalidScheduleRange):
            status, detail = 422, "Invalid schedule date range. Maximum range is 366 days."
        elif isinstance(error, ScheduleEventNotFound):
            status, detail = 404, "Schedule event or imported group not found."
        else:
            status, detail = 503, "Schedule synchronization is unavailable."
            log_failure(logging.getLogger(__name__), "schedule.sync_unavailable", error)
        return JSONResponse(
            {"detail": detail}, status_code=status, headers={"Cache-Control": "no-store"}
        )

    for error_type in (InvalidScheduleRange, ScheduleEventNotFound, ScheduleSyncUnavailable):
        application.add_exception_handler(error_type, schedule_error)
    application.add_exception_handler(AcademicProfileRequired, missing_profile)
    application.include_router(router)

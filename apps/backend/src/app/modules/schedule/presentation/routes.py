from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Path, Query, Request
from fastapi.responses import JSONResponse

from app.modules.academics.presentation.routes import Academics, IdentifierPath, no_store
from app.modules.auth.presentation.dependencies import CurrentSession, Database, get_current_session
from app.modules.schedule.application.provider import (
    Announcement,
    AnnouncementPage,
    Schedule,
    ScheduleProvider,
    UpdateDate,
)
from app.modules.schedule.application.schedule import AcademicProfileRequired, ScheduleService

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

    application.add_exception_handler(AcademicProfileRequired, missing_profile)
    application.include_router(router)

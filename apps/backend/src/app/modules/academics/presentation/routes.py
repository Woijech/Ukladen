from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Path, Request, Response
from fastapi.responses import JSONResponse

from app.modules.academics.application.directory import (
    Department,
    Faculty,
    InvalidUniversityRequest,
    Room,
    Speciality,
    Teacher,
    UniversityDirectory,
    UniversityEntityNotFound,
)
from app.modules.academics.application.ports import AcademicProvider, AcademicProviderUnavailable
from app.modules.academics.application.profile import AcademicService
from app.modules.academics.domain.profile import AcademicProfileConflict, InvalidAcademicSelection
from app.modules.academics.infrastructure.repository import SqlAlchemyAcademicProfileRepository
from app.modules.academics.presentation.schemas import (
    AcademicProfilePatch,
    AcademicProfileResponse,
    GroupContextResponse,
    UniversityGroupResponse,
)
from app.modules.auth.presentation.dependencies import CurrentSession, Database, require_csrf
from app.modules.users.infrastructure.repository import SqlAlchemyUserAuthentication


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/api/v1/academics", tags=["academics"], dependencies=[Depends(no_store)])
IdentifierPath = Annotated[int, Path(gt=0, le=2**63 - 1)]


def get_directory(request: Request) -> UniversityDirectory:
    return request.app.state.university_provider


Directory = Annotated[UniversityDirectory, Depends(get_directory)]


def get_academic_provider(request: Request) -> AcademicProvider:
    return request.app.state.academic_provider


Provider = Annotated[AcademicProvider, Depends(get_academic_provider)]


def get_academics(database: Database, provider: Provider) -> AcademicService:
    return AcademicService(
        SqlAlchemyAcademicProfileRepository(database),
        SqlAlchemyUserAuthentication(database),
        provider,
    )


Academics = Annotated[AcademicService, Depends(get_academics)]


@router.get("/groups/{group_id}", response_model=UniversityGroupResponse)
def get_group(
    group_id: IdentifierPath, current: CurrentSession, academics: Academics
) -> UniversityGroupResponse:
    return UniversityGroupResponse.model_validate(academics.get_group(group_id))


@router.get("/teachers", response_model=list[Teacher])
def list_teachers(current: CurrentSession, directory: Directory) -> list[Teacher]:
    return directory.list_teachers()


@router.get("/teachers/{teacher_id}", response_model=Teacher)
def get_teacher(
    teacher_id: IdentifierPath, current: CurrentSession, directory: Directory
) -> Teacher:
    return directory.get_teacher(teacher_id)


@router.get("/faculties", response_model=list[Faculty])
def list_faculties(current: CurrentSession, directory: Directory) -> list[Faculty]:
    return directory.list_faculties()


@router.get("/departments", response_model=list[Department])
def list_departments(current: CurrentSession, directory: Directory) -> list[Department]:
    return directory.list_departments()


@router.get("/specialities", response_model=list[Speciality])
def list_specialities(current: CurrentSession, directory: Directory) -> list[Speciality]:
    return directory.list_specialities()


@router.get("/rooms", response_model=list[Room])
def list_rooms(current: CurrentSession, directory: Directory) -> list[Room]:
    return directory.list_rooms()


@router.get("/groups", response_model=list[UniversityGroupResponse])
def list_groups(
    current: CurrentSession, academics: Academics, response: Response
) -> list[UniversityGroupResponse]:
    result = [UniversityGroupResponse.model_validate(group) for group in academics.list_groups()]
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("/groups/{group_id}/context", response_model=GroupContextResponse)
def get_group_context(
    group_id: Annotated[int, Path(gt=0, le=2**63 - 1)],
    current: CurrentSession,
    academics: Academics,
    response: Response,
) -> GroupContextResponse:
    result = GroupContextResponse.model_validate(academics.get_context(group_id))
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("/me", response_model=AcademicProfileResponse | None)
def get_profile(
    current: CurrentSession,
    database: Database,
    academics: Academics,
    response: Response,
) -> AcademicProfileResponse | None:
    with database.begin():
        profile = academics.get(current.user_id)
        result = AcademicProfileResponse.model_validate(profile) if profile else None
    response.headers["Cache-Control"] = "no-store"
    return result


@router.patch("/me", response_model=AcademicProfileResponse, dependencies=[Depends(require_csrf)])
def update_profile(
    payload: AcademicProfilePatch,
    current: CurrentSession,
    database: Database,
    academics: Academics,
    response: Response,
) -> AcademicProfileResponse:
    with database.begin():
        current_profile = academics.get(current.user_id)
    prepared = academics.prepare(current_profile, payload.model_dump(exclude_unset=True))
    with database.begin():
        result = AcademicProfileResponse.model_validate(academics.update(current.user_id, prepared))
    response.headers["Cache-Control"] = "no-store"
    return result


def install_academics(application: FastAPI) -> None:
    def academic_error(request: Request, error: Exception) -> JSONResponse:
        if isinstance(error, UniversityEntityNotFound):
            status, detail = 404, "University entity not found."
        elif isinstance(error, InvalidUniversityRequest):
            status, detail = 422, "Invalid university request."
        elif isinstance(error, InvalidAcademicSelection):
            status, detail = 422, "Invalid academic selection."
        elif isinstance(error, AcademicProfileConflict):
            status, detail = 409, "Academic group changed. Reload the profile and retry."
        else:
            status, detail = 503, "Service unavailable."
        return JSONResponse(
            {"detail": detail}, status_code=status, headers={"Cache-Control": "no-store"}
        )

    for error_type in (
        InvalidAcademicSelection,
        AcademicProfileConflict,
        AcademicProviderUnavailable,
        UniversityEntityNotFound,
        InvalidUniversityRequest,
    ):
        application.add_exception_handler(error_type, academic_error)
    application.include_router(router)

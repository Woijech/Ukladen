from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.modules.academics.application.ports import AcademicProvider
from app.modules.academics.application.profile import AcademicService
from app.modules.academics.infrastructure.repository import SqlAlchemyAcademicProfileRepository
from app.modules.ai.application.source_queries import ReadQuery, SearchRead
from app.modules.ai.application.sources import WorkspaceSourceService
from app.modules.calendar.application.composition import CalendarCompositionService
from app.modules.calendar.application.service import CalendarService
from app.modules.calendar.domain.events import InvalidCalendarInput
from app.modules.calendar.infrastructure.repository import SqlAlchemyCalendarRepository
from app.modules.materials.application.excerpts import MaterialExcerptService
from app.modules.materials.domain.materials import InvalidMaterialInput, MaterialNotFound
from app.modules.materials.infrastructure.excerpts import SqlAlchemyExtractedTextReader
from app.modules.materials.infrastructure.repository import SqlAlchemyMaterialRepository
from app.modules.materials.infrastructure.search import SqlAlchemyMaterialSearch
from app.modules.notes.application.service import NoteService
from app.modules.notes.domain.pages import InvalidPageInput, PageConflict, PageNotFound
from app.modules.notes.infrastructure.repository import SqlAlchemyPageRepository
from app.modules.notes.infrastructure.search import SqlAlchemyPageSearch
from app.modules.schedule.application.queries import ScheduleQueryService
from app.modules.schedule.infrastructure.storage import SqlAlchemyScheduleStore
from app.modules.search.application.evidence import EvidenceResult
from app.modules.search.application.service import SearchService
from app.modules.search.domain.search import InvalidSearchInput
from app.modules.users.domain.profile import ProfileUnavailable
from app.modules.users.infrastructure.repository import (
    SqlAlchemyProfileRepository,
    SqlAlchemyUserAuthentication,
)
from app.modules.workspace.application.database_calendar import DatabaseCalendarService
from app.modules.workspace.application.database_content import DatabaseContentService
from app.modules.workspace.application.database_views import DatabaseViewService
from app.modules.workspace.application.databases import DatabaseService
from app.modules.workspace.domain.organization import (
    InvalidWorkspaceInput,
    WorkspaceConflict,
    WorkspaceNotFound,
)
from app.modules.workspace.infrastructure.database_content import SqlAlchemyDatabaseContent
from app.modules.workspace.infrastructure.database_views import SqlAlchemyDatabaseViews
from app.modules.workspace.infrastructure.databases import SqlAlchemyDatabases


class SqlAlchemySourceReader:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        academics: AcademicProvider,
        stale_after_seconds: int,
        *,
        embeddings=None,
    ) -> None:
        self.embeddings = embeddings
        self.sessions, self.academics, self.stale_after_seconds = (
            sessions,
            academics,
            stale_after_seconds,
        )

    def service(self, database: Session) -> WorkspaceSourceService:
        users = SqlAlchemyUserAuthentication(database)
        notes = NoteService(SqlAlchemyPageRepository(database), users)
        views = DatabaseViewService(
            SqlAlchemyDatabaseViews(database),
            DatabaseContentService(
                SqlAlchemyDatabaseContent(database),
                DatabaseService(SqlAlchemyDatabases(database), notes),
            ),
        )
        calendar = CalendarService(
            SqlAlchemyCalendarRepository(database),
            SqlAlchemyProfileRepository(database),
            AcademicService(SqlAlchemyAcademicProfileRepository(database), users, self.academics),
            ScheduleQueryService(SqlAlchemyScheduleStore(self.sessions, read_session=database)),
            stale_after_seconds=self.stale_after_seconds,
        )
        return WorkspaceSourceService(
            notes,
            SearchService(
                users, SqlAlchemyPageSearch(database), SqlAlchemyMaterialSearch(database)
            ),
            MaterialExcerptService(
                SqlAlchemyMaterialRepository(database),
                users,
                SqlAlchemyExtractedTextReader(database),
            ),
            views,
            CalendarCompositionService(calendar, DatabaseCalendarService(views)),
        )

    def read(self, user_id: UUID, query: ReadQuery) -> EvidenceResult:
        try:
            if isinstance(query, SearchRead) and self.embeddings is not None:
                from app.modules.search.infrastructure.hybrid import HybridSearch

                return HybridSearch(self.sessions, self.embeddings).read(user_id, query)
            with self.sessions() as database, database.begin():
                database.connection(execution_options={"isolation_level": "REPEATABLE READ"})
                database.execute(text("SET LOCAL statement_timeout = '5s'"))
                database.execute(text("SET TRANSACTION READ ONLY"))
                return self.service(database).read(user_id, query)
        except PageNotFound, PageConflict, MaterialNotFound, WorkspaceNotFound, ProfileUnavailable:
            return EvidenceResult(status="not_found")
        except (
            InvalidPageInput,
            InvalidMaterialInput,
            InvalidSearchInput,
            InvalidCalendarInput,
            InvalidWorkspaceInput,
        ):
            return EvidenceResult(status="invalid")
        except ValidationError:
            return EvidenceResult(status="limit", warnings=("reduce_requested_range_or_columns",))
        except SQLAlchemyError, WorkspaceConflict:
            return EvidenceResult(status="unavailable")

    def context(self, user_id: UUID) -> str:
        with self.sessions() as database, database.begin():
            profile = SqlAlchemyProfileRepository(database).get_active(user_id)
            if profile is None:
                raise ProfileUnavailable()
            now = datetime.now(UTC).astimezone(ZoneInfo(profile.timezone))
            return f"Current profile time: {now.isoformat()}; timezone: {profile.timezone}."

from typing import Literal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.relations.domain.links import CalendarPageLink
from app.modules.relations.infrastructure.orm import CalendarPageLinkModel


def link_entity(row: CalendarPageLinkModel) -> CalendarPageLink:
    source: Literal["personal", "official"] = "personal" if row.personal_event_id else "official"
    event_id = row.personal_event_id or row.official_event_id
    assert event_id is not None
    return CalendarPageLink(row.id, row.user_id, row.page_id, source, event_id, row.created_at)


class SqlAlchemyCalendarPageLinks:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _target(source: Literal["personal", "official"]):
        return (
            CalendarPageLinkModel.personal_event_id
            if source == "personal"
            else CalendarPageLinkModel.official_event_id
        )

    def put(self, link: CalendarPageLink) -> CalendarPageLink:
        target = self._target(link.source)
        self.session.execute(
            insert(CalendarPageLinkModel)
            .values(
                id=link.id,
                user_id=link.user_id,
                page_id=link.page_id,
                **{target.key: link.event_id},
                created_at=link.created_at,
            )
            .on_conflict_do_nothing(index_elements=[CalendarPageLinkModel.page_id, target])
        )
        row = self.session.scalar(
            select(CalendarPageLinkModel).where(
                CalendarPageLinkModel.user_id == link.user_id,
                CalendarPageLinkModel.page_id == link.page_id,
                target == link.event_id,
            )
        )
        assert row is not None
        return link_entity(row)

    def delete(
        self, user_id: UUID, source: Literal["personal", "official"], event_id: UUID, page_id: UUID
    ) -> bool:
        return (
            self.session.scalar(
                delete(CalendarPageLinkModel)
                .where(
                    CalendarPageLinkModel.user_id == user_id,
                    CalendarPageLinkModel.page_id == page_id,
                    self._target(source) == event_id,
                )
                .returning(CalendarPageLinkModel.id)
            )
            is not None
        )

    def for_event(
        self,
        user_id: UUID,
        source: Literal["personal", "official"],
        event_id: UUID,
        limit: int,
        offset: int,
    ) -> list[CalendarPageLink]:
        return [
            link_entity(row)
            for row in self.session.scalars(
                select(CalendarPageLinkModel)
                .where(
                    CalendarPageLinkModel.user_id == user_id,
                    self._target(source) == event_id,
                )
                .order_by(CalendarPageLinkModel.created_at, CalendarPageLinkModel.id)
                .limit(limit)
                .offset(offset)
            )
        ]

    def for_page(
        self, user_id: UUID, page_id: UUID, limit: int, offset: int
    ) -> list[CalendarPageLink]:
        return [
            link_entity(row)
            for row in self.session.scalars(
                select(CalendarPageLinkModel)
                .where(
                    CalendarPageLinkModel.user_id == user_id,
                    CalendarPageLinkModel.page_id == page_id,
                )
                .order_by(CalendarPageLinkModel.created_at, CalendarPageLinkModel.id)
                .limit(limit)
                .offset(offset)
            )
        ]

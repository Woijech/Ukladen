from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.modules.ai.application.reviews import ReviewConfiguration, SavedReviewSettings
from app.modules.ai.domain.state import AiConflict
from app.modules.ai.infrastructure.review_models import ReviewSettingsModel


class SqlAlchemyReviewSettings:
    def __init__(self, database: Session):
        self.database = database

    def get(self, user_id: UUID) -> SavedReviewSettings:
        row = self.database.get(ReviewSettingsModel, user_id, populate_existing=True)
        return (
            SavedReviewSettings(
                ReviewConfiguration.model_validate(row.configuration),
                row.version,
                row.offering_version,
            )
            if row
            else SavedReviewSettings()
        )

    def save(self, user_id: UUID, value: SavedReviewSettings, expected_version: int) -> None:
        row = self.database.get(ReviewSettingsModel, user_id, populate_existing=True)
        state = {key: item for key, item in row.state.items() if key != "paused"} if row else {}
        values = dict(
            state=state,
            configuration=value.configuration.model_dump(mode="json"),
            version=value.version,
            offering_version=value.offering_version,
            next_scan_at=datetime.now(UTC),
        )
        if expected_version == 0:
            self.database.add(ReviewSettingsModel(user_id=user_id, **values))
        elif (
            self.database.scalar(
                update(ReviewSettingsModel)
                .where(
                    ReviewSettingsModel.user_id == user_id,
                    ReviewSettingsModel.version == expected_version,
                )
                .values(**values)
                .returning(ReviewSettingsModel.user_id)
            )
            is None
        ):
            raise AiConflict("Review settings changed.")
        self.database.flush()

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.modules.materials.application.ports import (
    MaterialRepository,
    MaterialStorage,
    MaterialTextIndex,
    TextExtractor,
)
from app.modules.materials.domain.materials import (
    DocumentExtractionError,
    Material,
    MaterialStorageUnavailable,
)
from app.modules.users.application.ports import UserAuthentication


@dataclass(frozen=True)
class ExtractionResult:
    text: str = ""
    error_code: str | None = None
    retryable: bool = False


class MaterialProcessingService:
    def __init__(
        self,
        repository: MaterialRepository,
        users: UserAuthentication,
        storage: MaterialStorage,
        extractor: TextExtractor,
        index: MaterialTextIndex,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.repository, self.users, self.storage = repository, users, storage
        self.extractor, self.index, self.now = extractor, index, now

    def claim(self, user_id: UUID, material_id: UUID) -> Material | None:
        if not self.users.lock_active(user_id):
            return None
        material, now = self.repository.get(user_id, material_id), self.now()
        if material is None or material.trashed_at is not None or material.kind != "file":
            return None
        if material.status != "pending" and not (
            material.status == "processing"
            and material.lease_until is not None
            and material.lease_until <= now
        ):
            return None
        if material.attempts >= 3:
            updated = replace(
                material,
                status="failed",
                lease_token=None,
                lease_until=None,
                error_code="processing_timeout",
                version=material.version + 1,
                updated_at=now,
            )
            self.repository.save(updated, material.version)
            return None
        claimed = replace(
            material,
            status="processing",
            attempts=material.attempts + 1,
            lease_token=uuid4(),
            lease_until=now + timedelta(minutes=2),
            version=material.version + 1,
            updated_at=now,
        )
        self.repository.save(claimed, material.version)
        return claimed

    def execute(self, material: Material) -> ExtractionResult:
        try:
            body = self.storage.get(material.storage_key, material.size_bytes)
            if body is None:
                raise MaterialStorageUnavailable()
            with body:
                assert material.filename is not None
                return ExtractionResult(self.extractor.extract(body, material.filename))
        except DocumentExtractionError as error:
            return ExtractionResult(error_code=error.code)
        except MaterialStorageUnavailable:
            return ExtractionResult(error_code="storage_unavailable", retryable=True)

    def complete(self, work: Material, result: ExtractionResult) -> None:
        if not self.users.lock_active(work.user_id):
            return
        current = self.repository.get(work.user_id, work.id)
        if (
            current is None
            or current.status != "processing"
            or current.lease_token != work.lease_token
        ):
            return
        status, error = "ready", result.error_code
        if current.trashed_at is not None:
            status, error = "pending", None
        elif error is not None:
            status = "pending" if result.retryable and current.attempts < 3 else "failed"
        else:
            try:
                self.index.put(current.user_id, current.id, result.text)
                error = "no_extractable_text" if not result.text else None
            except DocumentExtractionError as failure:
                status, error = "failed", failure.code
        self.repository.save(
            replace(
                current,
                status=status,
                error_code=error,
                lease_token=None,
                lease_until=None,
                updated_at=self.now(),
                version=current.version + 1,
            ),
            current.version,
        )

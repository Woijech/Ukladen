from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.materials.application.excerpts import ExtractedTextReader, MaterialExcerptService
from app.modules.materials.application.ports import MaterialRepository
from app.modules.materials.domain.materials import InvalidMaterialInput, MaterialNotFound
from app.modules.search.application.evidence import EvidenceResult
from app.modules.users.application.ports import UserAuthentication
from app.modules.users.domain.profile import ProfileUnavailable


def test_excerpt_ownership_state_and_unicode_ranges() -> None:
    owner, identifier = uuid4(), uuid4()
    materials, users, text = (
        Mock(spec=MaterialRepository),
        Mock(spec=UserAuthentication),
        Mock(spec=ExtractedTextReader),
    )
    material = Mock(
        id=identifier, title="Lecture", version=3, trashed_at=None, kind="file", status="ready"
    )
    materials.get.return_value = material
    users.is_active.return_value = True
    text.read.return_value = ("я🙂", 5)
    service = MaterialExcerptService(materials, users, text)
    result = service.read(owner, identifier, 1, 2)
    assert result and result.text == "я🙂" and result.total_characters == 5
    assert result.version == 3 and result.offset == 1
    text.read.assert_called_once_with(owner, identifier, 1, 2)
    text.reset_mock()
    material.status = "processing"
    assert service.read(owner, identifier) is None
    material.trashed_at = datetime.now(UTC)
    with pytest.raises(MaterialNotFound):
        service.read(owner, identifier)
    materials.get.return_value = None
    with pytest.raises(MaterialNotFound):
        service.read(owner, identifier)
    users.is_active.return_value = False
    with pytest.raises(ProfileUnavailable):
        service.read(owner, identifier)
    text.read.assert_not_called()


@pytest.mark.parametrize("offset,limit", [(-1, 1), (True, 1), (0, 2001), (0, False)])
def test_excerpt_rejects_invalid_ranges_before_read(offset, limit) -> None:
    text = Mock(spec=ExtractedTextReader)
    service = MaterialExcerptService(Mock(), Mock(), text)
    with pytest.raises(InvalidMaterialInput):
        service.read(uuid4(), uuid4(), offset, limit)
    text.read.assert_not_called()


def test_evidence_budget_counts_utf8_and_preserves_unknown_coverage() -> None:
    assert EvidenceResult(status="unavailable").coverage == "none"
    with pytest.raises(ValidationError):
        EvidenceResult(data="🙂" * 4096)

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

TargetType = Literal["page", "personal", "official"]
TargetFilter = Literal["page", "personal", "official", "event"]


@dataclass(frozen=True)
class Membership:
    id: UUID
    user_id: UUID
    organization_id: UUID
    target_type: TargetType
    target_id: UUID
    created_at: datetime

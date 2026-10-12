import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

OrganizationKind = Literal["collection", "tag"]


class InvalidWorkspaceInput(ValueError):
    pass


class WorkspaceNotFound(Exception):
    pass


class WorkspaceConflict(Exception):
    pass


def organization_values(name: object, color: object) -> tuple[str, str | None]:
    if not isinstance(name, str):
        raise InvalidWorkspaceInput()
    name = name.strip()
    if not 1 <= len(name) <= 100 or "\x00" in name:
        raise InvalidWorkspaceInput()
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        raise InvalidWorkspaceInput() from None
    if color is not None:
        if not isinstance(color, str) or re.fullmatch(r"#[0-9a-fA-F]{6}", color) is None:
            raise InvalidWorkspaceInput()
        color = color.lower()
    return name, color


def require_version(actual: int, expected: int) -> None:
    if type(expected) is not int or not 1 <= expected <= 2**31 - 2:
        raise InvalidWorkspaceInput()
    if actual != expected:
        raise WorkspaceConflict()


def pagination(limit: int, offset: int) -> None:
    if (
        type(limit) is not int
        or type(offset) is not int
        or not 1 <= limit <= 200
        or not 0 <= offset <= 2**31 - 1
    ):
        raise InvalidWorkspaceInput()


@dataclass(frozen=True)
class Organization:
    id: UUID
    user_id: UUID
    kind: OrganizationKind
    name: str
    color: str | None
    version: int
    created_at: datetime
    updated_at: datetime

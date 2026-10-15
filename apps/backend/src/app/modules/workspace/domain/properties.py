import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal, cast
from uuid import UUID

from app.core.urls import http_url
from app.modules.workspace.domain.organization import (
    InvalidWorkspaceInput,
    WorkspaceConflict,
    organization_values,
)

PropertyKind = Literal["text", "number", "checkbox", "select", "multi_select", "url", "date"]
PROPERTY_KINDS = ("text", "number", "checkbox", "select", "multi_select", "url", "date")
type PropertyValue = str | int | float | bool | None | list[str] | dict[str, str | None]


def property_id(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            pass
    raise InvalidWorkspaceInput()


@dataclass(frozen=True)
class PropertyOption:
    id: UUID
    name: str


@dataclass(frozen=True)
class PropertySpec:
    name: str
    kind: PropertyKind
    options: tuple[PropertyOption, ...] = ()


def property_spec(name: object, kind: object, options: object = ()) -> PropertySpec:
    name, _ = organization_values(name, None)
    if not isinstance(kind, str) or kind not in PROPERTY_KINDS:
        raise InvalidWorkspaceInput()
    if not isinstance(options, (list, tuple)) or len(options) > 100:
        raise InvalidWorkspaceInput()
    if options and kind not in ("select", "multi_select"):
        raise InvalidWorkspaceInput()
    result: list[PropertyOption] = []
    for option in options:
        if not isinstance(option, Mapping) or option.keys() != {"id", "name"}:
            raise InvalidWorkspaceInput()
        label, _ = organization_values(option["name"], None)
        result.append(PropertyOption(property_id(option["id"]), label))
    if len({item.id for item in result}) != len(result) or len(
        {item.name.casefold() for item in result}
    ) != len(result):
        raise InvalidWorkspaceInput()
    return PropertySpec(name, cast(PropertyKind, kind), tuple(result))


def date_value(value: object) -> dict[str, str | None]:
    if not isinstance(value, Mapping) or value.keys() - {"kind", "start", "end"}:
        raise InvalidWorkspaceInput()
    kind, start, end = value.get("kind"), value.get("start"), value.get("end")
    if kind not in ("date", "datetime") or not isinstance(start, str):
        raise InvalidWorkspaceInput()
    if end is not None and not isinstance(end, str):
        raise InvalidWorkspaceInput()
    try:
        if kind == "date":
            if any(
                re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", item) is None
                for item in (start, end)
                if item is not None
            ):
                raise ValueError()
            first, last = date.fromisoformat(start), date.fromisoformat(end or start)
            if first == date.min or last == date.max or last < first:
                raise ValueError()
            return {
                "kind": "date",
                "start": first.isoformat(),
                "end": last.isoformat() if end is not None else None,
            }
        if any(
            re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T.+", item) is None
            for item in (start, end)
            if item is not None
        ):
            raise ValueError()
        begins = datetime.fromisoformat(start)
        finishes = datetime.fromisoformat(end) if end is not None else None
        if begins.utcoffset() is None or (finishes is not None and finishes.utcoffset() is None):
            raise ValueError()
        begins = begins.astimezone(UTC)
        finishes = finishes.astimezone(UTC) if finishes is not None else None
        if finishes is not None and finishes <= begins:
            raise ValueError()
        return {
            "kind": "datetime",
            "start": begins.isoformat(),
            "end": finishes.isoformat() if finishes is not None else None,
        }
    except ValueError, OverflowError:
        raise InvalidWorkspaceInput() from None


def property_value(spec: PropertySpec, value: object) -> PropertyValue:
    if value is None:
        return None
    if spec.kind == "text":
        if not isinstance(value, str) or len(value) > 10000 or "\x00" in value:
            raise InvalidWorkspaceInput()
        try:
            value.encode("utf-8")
        except UnicodeError:
            raise InvalidWorkspaceInput() from None
        return value
    if spec.kind == "number":
        if type(value) not in (int, float) or not isinstance(value, (int, float)):
            raise InvalidWorkspaceInput()
        if not -9007199254740991 <= value <= 9007199254740991 or not math.isfinite(value):
            raise InvalidWorkspaceInput()
        return value
    if spec.kind == "checkbox":
        if type(value) is not bool:
            raise InvalidWorkspaceInput()
        return value
    if spec.kind == "url":
        try:
            return http_url(value)
        except ValueError:
            raise InvalidWorkspaceInput() from None
    if spec.kind in ("select", "multi_select"):
        raw = [value] if spec.kind == "select" else value
        if not isinstance(raw, (list, tuple)) or len(raw) > 100:
            raise InvalidWorkspaceInput()
        ids = [property_id(item) for item in raw]
        if len(set(ids)) != len(ids) or set(ids) - {item.id for item in spec.options}:
            raise InvalidWorkspaceInput()
        return str(ids[0]) if spec.kind == "select" else [str(item) for item in ids]
    return date_value(value)


def convert_property_value(
    previous: PropertySpec, updated: PropertySpec, value: object
) -> PropertyValue:
    original = property_value(previous, value)
    if previous.kind != updated.kind and original is not None:
        if previous.kind == "select" and updated.kind == "multi_select":
            original = [str(original)]
        elif (
            previous.kind == "multi_select"
            and updated.kind == "select"
            and isinstance(original, list)
            and len(original) <= 1
        ):
            original = original[0] if original else None
        elif {previous.kind, updated.kind} != {"text", "url"}:
            raise WorkspaceConflict()
    try:
        return property_value(updated, original)
    except InvalidWorkspaceInput:
        raise WorkspaceConflict() from None

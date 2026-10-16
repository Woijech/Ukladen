from dataclasses import asdict, replace
from uuid import uuid4

import pytest

from app.modules.workspace.domain.organization import InvalidWorkspaceInput, WorkspaceConflict
from app.modules.workspace.domain.properties import (
    convert_property_value,
    date_value,
    property_spec,
    property_value,
)


@pytest.mark.parametrize(
    "kind,value",
    [
        ("text", "  Notes\n世界  "),
        ("number", 0),
        ("number", 2.5),
        ("checkbox", False),
        ("url", "https://example.com/path?q=1#part"),
        ("date", {"kind": "date", "start": "2028-02-29", "end": None}),
    ],
)
def test_typed_values_preserve_valid_inputs(kind: str, value: object) -> None:
    spec = property_spec(" Field ", kind)
    assert spec.name == "Field"
    assert property_value(spec, value) == value
    assert property_value(spec, None) is None


@pytest.mark.parametrize(
    "kind,value",
    [
        ("text", 1),
        ("text", "bad\x00text"),
        ("text", "bad\ud800text"),
        ("text", "x" * 10001),
        ("number", True),
        ("number", "1"),
        ("number", float("nan")),
        ("number", float("inf")),
        ("number", 9007199254740992),
        ("number", 10**1000),
        ("checkbox", 1),
        ("url", "javascript:alert(1)"),
        ("url", "https://user:secret@example.com"),
        ("url", "https://example.com:70000"),
        ("url", "https://example.com/\n"),
        ("url", "https://example.com/\\path"),
        ("select", str(uuid4())),
        ("multi_select", "invalid"),
    ],
)
def test_invalid_values_are_rejected(kind: str, value: object) -> None:
    with pytest.raises(InvalidWorkspaceInput):
        property_value(property_spec("Field", kind), value)


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"kind": "date", "start": "2026-02-29"},
        {"kind": "date", "start": "2026-10-20", "end": "2026-10-19"},
        {"kind": "date", "start": "2026-10-20T12:00:00Z"},
        {"kind": "date", "start": "0001-01-01"},
        {"kind": "date", "start": "9999-12-31"},
        {"kind": "datetime", "start": "2026-10-20T12:00:00"},
        {"kind": "datetime", "start": "20261020T12:00:00Z"},
        {"kind": "datetime", "start": "2026-10-20T12:00:00Z", "end": "2026-10-20T15:00:00+03:00"},
        {"kind": "date", "start": "2026-10-20", "sql": "select 1"},
        {"kind": "date", "start": "2026-10-20", "end": False},
    ],
)
def test_dates_have_explicit_kind_and_valid_ranges(value: object) -> None:
    with pytest.raises(InvalidWorkspaceInput):
        date_value(value)


def test_date_only_and_offset_ranges_keep_their_meaning() -> None:
    assert date_value({"kind": "date", "start": "2026-10-20", "end": "2026-10-20"}) == {
        "kind": "date",
        "start": "2026-10-20",
        "end": "2026-10-20",
    }
    assert date_value(
        {
            "kind": "datetime",
            "start": "2026-10-25T02:30:00+02:00",
            "end": "2026-10-25T02:30:00+01:00",
        }
    ) == {
        "kind": "datetime",
        "start": "2026-10-25T00:30:00+00:00",
        "end": "2026-10-25T01:30:00+00:00",
    }


def test_select_ids_survive_labels_and_safe_type_conversion() -> None:
    first, second = uuid4(), uuid4()
    spec = property_spec(
        "Status", "select", [{"id": first, "name": "Planned"}, {"id": second, "name": "Done"}]
    )
    updated = property_spec(
        "Renamed",
        "multi_select",
        [asdict(replace(spec.options[0], name="Pending")), asdict(spec.options[1])],
    )
    assert convert_property_value(spec, updated, str(first)) == [str(first)]
    assert convert_property_value(updated, spec, [str(first)]) == str(first)
    assert convert_property_value(updated, spec, []) is None
    with pytest.raises(WorkspaceConflict):
        convert_property_value(updated, spec, [str(first), str(second)])
    with pytest.raises(WorkspaceConflict):
        convert_property_value(spec, replace(spec, options=()), str(first))
    with pytest.raises(InvalidWorkspaceInput):
        property_value(updated, [str(first), str(first)])


def test_conversions_never_guess_or_discard_values() -> None:
    text, link, number = (property_spec("Field", kind) for kind in ("text", "url", "number"))
    assert convert_property_value(text, link, "https://example.com") == "https://example.com"
    assert convert_property_value(link, text, "https://example.com") == "https://example.com"
    assert convert_property_value(text, number, None) is None
    for before, after, value in (
        (text, link, "plain text"),
        (text, number, "001"),
        (number, text, 1),
    ):
        with pytest.raises(WorkspaceConflict):
            convert_property_value(before, after, value)


@pytest.mark.parametrize(
    "name,kind,options",
    [
        (" ", "text", []),
        ("Field", "formula", []),
        ("Field", "select", {}),
        ("Field", "text", [{"id": str(uuid4()), "name": "Unexpected"}]),
        ("Field", "select", [{"id": "bad", "name": "Bad ID"}]),
        (
            "Field",
            "select",
            [{"id": str(uuid4()), "name": "Done"}, {"id": str(uuid4()), "name": "done"}],
        ),
    ],
)
def test_property_definitions_are_bounded_and_typed(
    name: object, kind: object, options: object
) -> None:
    with pytest.raises(InvalidWorkspaceInput):
        property_spec(name, kind, options)

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.modules.workspace.domain.database_views import parse_query, query_value, validate_query
from app.modules.workspace.domain.databases import DatabaseProperty
from app.modules.workspace.domain.organization import InvalidWorkspaceInput


def definition(kind: str = "text") -> DatabaseProperty:
    from typing import cast

    from app.modules.workspace.domain.properties import PropertyKind

    return DatabaseProperty(
        id=uuid4(),
        user_id=uuid4(),
        database_id=uuid4(),
        name="Field",
        kind=cast(PropertyKind, kind),
        position=0,
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {"version": True},
        {"version": 2},
        {"sql": "select 1"},
        {"filters": [{}]},
        {"filters": [{"property_id": str(uuid4()), "operator": "sql"}]},
        {"sorts": [{"property_id": str(uuid4()), "direction": "random"}]},
        {"columns": [True]},
        {"columns": [str(uuid4())] * 2},
        {"sorts": [{"property_id": str(uuid4())}] * 4},
    ],
)
def test_invalid_query_shapes(value: object) -> None:
    with pytest.raises(InvalidWorkspaceInput):
        parse_query(value)


def test_query_rules_use_active_typed_properties() -> None:
    text, number, multi = definition(), definition("number"), definition("multi_select")
    query = {
        "version": 1,
        "columns": [str(number.id), str(text.id)],
        "filters": [{"property_id": str(number.id), "operator": "gte", "value": 0}],
        "sorts": [{"property_id": str(number.id), "direction": "desc"}],
    }
    normalized = validate_query(query, [text, number])
    assert query_value(normalized) == query
    for invalid in (
        {"columns": [str(uuid4())]},
        {"filters": [{"property_id": str(text.id), "operator": "gt", "value": "A"}]},
        {"filters": [{"property_id": str(number.id), "operator": "eq", "value": True}]},
        {"filters": [{"property_id": str(number.id), "operator": "is_empty", "value": 1}]},
        {"sorts": [{"property_id": str(multi.id)}]},
        {
            "filters": [{"property_id": str(text.id), "operator": "contains", "value": "x" * 10000}]
            * 7
        },
    ):
        with pytest.raises(InvalidWorkspaceInput):
            validate_query(invalid, [text, number, multi])

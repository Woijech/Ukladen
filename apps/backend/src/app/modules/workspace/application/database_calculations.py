"""Owned relation validation and bounded, read-only record calculations."""

from dataclasses import dataclass, field
from uuid import UUID

from app.modules.workspace.application.database_content_ports import DatabaseContentRepository
from app.modules.workspace.application.databases import DatabaseService
from app.modules.workspace.domain.databases import DatabaseProperty, DatabaseRecord
from app.modules.workspace.domain.formulas import (
    CalculationError,
    calculate_formula,
    formula_tree,
    numeric,
)
from app.modules.workspace.domain.organization import (
    InvalidWorkspaceInput,
    WorkspaceConflict,
    WorkspaceNotFound,
)
from app.modules.workspace.domain.properties import PropertySpec, PropertyValue


@dataclass
class RecordCalculations:
    values: dict[str, PropertyValue] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    related_titles: dict[str, str] = field(default_factory=dict)


def validate_calculation(
    user_id: UUID,
    spec: PropertySpec,
    definitions: list[DatabaseProperty],
    databases: DatabaseService,
    repository: DatabaseContentRepository,
) -> None:
    active = {item.id: item for item in definitions if item.trashed_at is None}
    if spec.kind == "relation":
        assert spec.relation_database_id is not None
        databases.get(user_id, spec.relation_database_id, active=True)
    elif spec.kind == "formula":
        _, references = formula_tree(spec.calculation["expression"])
        if any(
            identifier not in active or active[identifier].kind != "number"
            for identifier in references
        ):
            raise InvalidWorkspaceInput("Formulas require active numeric input properties.")
    elif spec.kind == "rollup":
        relation = active.get(UUID(spec.calculation["relation_property_id"]))
        if relation is None or relation.kind != "relation" or relation.relation_database_id is None:
            raise InvalidWorkspaceInput("A rollup requires an active relation property.")
        databases.get(user_id, relation.relation_database_id, active=True)
        if spec.calculation["operation"] != "count":
            target = UUID(spec.calculation["value_property_id"])
            properties = repository.properties(user_id, relation.relation_database_id)
            if not any(
                item.id == target and item.kind == "number" and item.trashed_at is None
                for item in properties
            ):
                raise InvalidWorkspaceInput(
                    "A numeric rollup requires an active numeric target property."
                )


def validate_relations(
    user_id: UUID,
    definitions: list[DatabaseProperty],
    values: dict[str, PropertyValue],
    databases: DatabaseService,
    repository: DatabaseContentRepository,
) -> None:
    for definition in definitions:
        value = values.get(str(definition.id))
        if definition.kind != "relation" or not value:
            continue
        assert definition.relation_database_id is not None and isinstance(value, list)
        databases.get(user_id, definition.relation_database_id, active=True)
        records = repository.related_records(
            user_id, definition.relation_database_id, tuple(UUID(item) for item in value)
        )
        if len(records) != len(value):
            raise WorkspaceNotFound()
        pages = databases.notes.summaries(user_id, tuple(item.page_id for item in records))
        if any(
            item.trashed_at is not None
            or item.page_id not in pages
            or pages[item.page_id].trashed_at is not None
            for item in records
        ):
            raise WorkspaceConflict("Related records must be active.")


def record_calculations(
    user_id: UUID,
    definitions: list[DatabaseProperty],
    records: list[DatabaseRecord],
    databases: DatabaseService,
    repository: DatabaseContentRepository,
) -> dict[UUID, RecordCalculations]:
    if not records:
        return {}
    active = {item.id: item for item in definitions if item.trashed_at is None}
    relations = [item for item in active.values() if item.kind == "relation"]
    requested: dict[UUID, set[UUID]] = {}
    for relation in relations:
        assert relation.relation_database_id is not None
        requested.setdefault(relation.relation_database_id, set())
        for record in records:
            value = record.values.get(str(relation.id))
            if isinstance(value, list):
                requested.setdefault(relation.relation_database_id, set()).update(
                    UUID(item) for item in value
                )
    over_limit = sum(len(items) for items in requested.values()) > 2000 or len(requested) > 20
    related: dict[UUID, DatabaseRecord] = {}
    target_definitions: dict[UUID, list[DatabaseProperty]] = {}
    if not over_limit:
        for database_id, identifiers in requested.items():
            try:
                databases.get(user_id, database_id, active=True)
            except WorkspaceNotFound, WorkspaceConflict:
                continue
            target_definitions[database_id] = repository.properties(user_id, database_id)
            related.update(
                {
                    item.id: item
                    for item in repository.related_records(user_id, database_id, tuple(identifiers))
                    if item.trashed_at is None
                }
            )
    pages = (
        databases.notes.summaries(user_id, tuple({item.page_id for item in related.values()}))
        if related
        else {}
    )
    related = {
        identifier: item
        for identifier, item in related.items()
        if item.page_id in pages and pages[item.page_id].trashed_at is None
    }
    results: dict[UUID, RecordCalculations] = {}
    for record in records:
        result = RecordCalculations()
        results[record.id] = result
        for relation in relations:
            value = record.values.get(str(relation.id))
            if isinstance(value, list):
                result.related_titles.update(
                    {
                        identifier: pages[related[UUID(identifier)].page_id].title
                        for identifier in value
                        if UUID(identifier) in related
                    }
                )
        for definition in active.values():
            if definition.kind not in ("formula", "rollup"):
                continue
            key = str(definition.id)
            try:
                if definition.kind == "formula":
                    _, references = formula_tree(definition.calculation["expression"])
                    if any(
                        identifier not in active or active[identifier].kind != "number"
                        for identifier in references
                    ):
                        raise CalculationError("source_unavailable")
                    result.values[key] = calculate_formula(
                        definition.calculation["expression"], record.values
                    )
                    continue
                if over_limit:
                    raise CalculationError("calculation_limit")
                relation = active.get(UUID(definition.calculation["relation_property_id"]))
                if (
                    relation is None
                    or relation.kind != "relation"
                    or relation.relation_database_id is None
                ):
                    raise CalculationError("source_unavailable")
                if relation.relation_database_id not in target_definitions:
                    raise CalculationError("source_unavailable")
                raw = record.values.get(str(relation.id)) or []
                if not isinstance(raw, list):
                    raise CalculationError("source_unavailable")
                selected = [related.get(UUID(identifier)) for identifier in raw]
                if any(
                    item is None or item.database_id != relation.relation_database_id
                    for item in selected
                ):
                    raise CalculationError("source_unavailable")
                operation = definition.calculation["operation"]
                if operation == "count":
                    result.values[key] = len(selected)
                    continue
                target = UUID(definition.calculation["value_property_id"])
                if not any(
                    item.id == target and item.kind == "number" and item.trashed_at is None
                    for item in target_definitions.get(relation.relation_database_id, [])
                ):
                    raise CalculationError("source_unavailable")
                numbers = [
                    numeric(item.values.get(str(target))) for item in selected if item is not None
                ]
                if operation != "sum" and not numbers:
                    raise CalculationError("empty_relation")
                value = (
                    sum(numbers)
                    if operation == "sum"
                    else sum(numbers) / len(numbers)
                    if operation == "average"
                    else min(numbers)
                    if operation == "min"
                    else max(numbers)
                )
                result.values[key] = numeric(value)
            except CalculationError as error:
                result.values[key] = None
                result.errors[key] = error.code
            except InvalidWorkspaceInput, KeyError, ValueError:
                result.values[key] = None
                result.errors[key] = "source_unavailable"
    return results

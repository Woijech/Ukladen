from uuid import UUID, uuid4

import pytest

from app.modules.workspace.domain.formulas import CalculationError, calculate_formula, formula_tree
from app.modules.workspace.domain.organization import InvalidWorkspaceInput
from app.modules.workspace.domain.properties import property_spec, property_value


@pytest.mark.parametrize(
    "expression",
    [
        '__import__("os").system("id")',
        "1 ** 100000000",
        "[1] * 2000",
        "(1).__class__",
        'prop("not-an-id")',
        "prop(1)",
        "True + 1",
        '"hello"',
        "sum([1, 2])",
        "1e300",
        "9" * 300,
        "+" * 100 + "1",
    ],
)
def test_formula_language_rejects_unbounded_or_executable_syntax(expression: str) -> None:
    with pytest.raises(InvalidWorkspaceInput):
        formula_tree(expression)


def test_formula_arithmetic_missing_inputs_and_numeric_bounds() -> None:
    identifier = str(uuid4())
    expression = f'(prop("{identifier}") + 2) * -3 / 2'
    assert calculate_formula(expression, {identifier: 4}) == -9
    assert formula_tree(expression)[1] == (UUID(identifier),)
    for value in (None, True, "4"):
        with pytest.raises(CalculationError, match="missing_numeric_input"):
            calculate_formula(expression, {identifier: value})
    with pytest.raises(CalculationError, match="division_by_zero"):
        calculate_formula("1 / 0", {})
    with pytest.raises(CalculationError, match="number_out_of_range"):
        calculate_formula("9007199254740991 * 2", {})


def test_computed_values_are_read_only_and_relations_have_bounded_unique_ids() -> None:
    formula = property_spec("Total", "formula", calculation={"expression": "1 + 2"})
    assert property_value(formula, None) is None
    with pytest.raises(InvalidWorkspaceInput):
        property_value(formula, 3)
    relation = property_spec("Related", "relation", relation_database_id=uuid4())
    identifier = str(uuid4())
    assert property_value(relation, [identifier]) == [identifier]
    for value in ([identifier, identifier], [identifier] * 101, ["invalid"], identifier):
        with pytest.raises(InvalidWorkspaceInput):
            property_value(relation, value)

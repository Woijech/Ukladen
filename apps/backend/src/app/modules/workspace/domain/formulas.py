"""Bounded arithmetic over stable numeric property identities; never evaluates code."""

import ast
import math
from collections.abc import Mapping
from operator import add, mod, mul, sub, truediv
from uuid import UUID

from app.modules.workspace.domain.organization import InvalidWorkspaceInput

MAX_NUMBER = 9007199254740991
OPERATORS = {ast.Add: add, ast.Sub: sub, ast.Mult: mul, ast.Div: truediv, ast.Mod: mod}


class CalculationError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def numeric(value: object) -> int | float:
    if type(value) not in (int, float) or not isinstance(value, int | float):
        raise CalculationError("missing_numeric_input")
    if abs(value) > MAX_NUMBER or not math.isfinite(value):
        raise CalculationError("number_out_of_range")
    return value


def formula_tree(expression: object) -> tuple[ast.Expression, tuple[UUID, ...]]:
    if not isinstance(expression, str) or not 1 <= len(expression) <= 2000:
        raise InvalidWorkspaceInput()
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError, ValueError, RecursionError:
        raise InvalidWorkspaceInput() from None
    if len(list(ast.walk(tree))) > 64:
        raise InvalidWorkspaceInput()
    references: list[UUID] = []

    def validate(node: ast.AST, depth: int = 0) -> None:
        if depth > 12:
            raise InvalidWorkspaceInput()
        if isinstance(node, ast.Constant):
            try:
                numeric(node.value)
            except CalculationError:
                raise InvalidWorkspaceInput() from None
        elif isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            validate(node.left, depth + 1)
            validate(node.right, depth + 1)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd | ast.USub):
            validate(node.operand, depth + 1)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "prop"
            and len(node.args) == 1
            and not node.keywords
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            try:
                references.append(UUID(node.args[0].value))
            except ValueError:
                raise InvalidWorkspaceInput() from None
        else:
            raise InvalidWorkspaceInput()

    validate(tree.body)
    return tree, tuple(dict.fromkeys(references))


def calculate_formula(expression: str, values: Mapping[str, object]) -> int | float:
    tree, _ = formula_tree(expression)

    def calculate(node: ast.AST) -> int | float:
        if isinstance(node, ast.Constant):
            return numeric(node.value)
        if isinstance(node, ast.Call):
            argument = node.args[0]
            assert isinstance(argument, ast.Constant)
            assert isinstance(argument.value, str)
            return numeric(values.get(str(UUID(argument.value))))
        if isinstance(node, ast.UnaryOp):
            value = calculate(node.operand)
            return numeric(-value if isinstance(node.op, ast.USub) else value)
        assert isinstance(node, ast.BinOp)
        try:
            return numeric(OPERATORS[type(node.op)](calculate(node.left), calculate(node.right)))
        except ZeroDivisionError:
            raise CalculationError("division_by_zero") from None
        except OverflowError:
            raise CalculationError("number_out_of_range") from None

    return calculate(tree.body)

"""Pure synthetic tools, never registered with an HTTP endpoint or business service."""

from langchain.tools import tool
from pydantic import BaseModel, ConfigDict, Field


class DoubleInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    value: int = Field(ge=1, le=100)


@tool(args_schema=DoubleInput)
def fake_double(value: int) -> dict[str, int]:
    """Double a bounded integer without changing application data."""
    return {"value": value * 2}


@tool(args_schema=DoubleInput)
def fake_reviewed_double(value: int) -> dict[str, int]:
    """Demonstrate review before a pure synthetic operation."""
    return {"value": value * 2}

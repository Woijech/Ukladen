import hashlib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.modules.ai.application.actions import ActionBatch
from app.modules.ai.application.source_queries import READ_QUERIES, SourceScope
from app.modules.search.application.evidence import EvidenceResult

DATASET = Path(__file__).with_name("scenarios.json")


class Fixture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str
    arguments: dict[str, Any]
    result: EvidenceResult
    fail_once: bool = False


class ExpectedCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    arguments: dict[str, Any]


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request: str
    script: list[dict[str, Any]] = Field(min_length=1)
    expected_tools: list[ExpectedCall]
    expected_status: Literal["completed", "interrupted", "failed", "limited"] = "completed"
    required_facts: list[str]
    supported_claims: list[str]
    required_citations: list[str] = []


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    category: str
    expected_result: str = Field(min_length=10)
    allowed_tools: list[str]
    forbidden_actions: list[str] = Field(min_length=1)
    invariants: list[str] = Field(min_length=1)
    source_scope: SourceScope | None = None
    source_only: bool = True
    forbidden_content: list[str] = []
    fixtures: list[Fixture]
    turns: list[Turn] = Field(min_length=1)


def load_suite() -> tuple[str, list[Scenario]]:
    raw = DATASET.read_bytes()
    cases = TypeAdapter(list[Scenario]).validate_json(raw)
    if len(cases) < 50 or len({s.id for s in cases}) != len(cases):
        raise ValueError("At least 50 uniquely identified scenarios are required.")
    for case in cases:
        for fixture in case.fixtures:
            READ_QUERIES[fixture.tool].model_validate(fixture.arguments)
        for turn in case.turns:
            for call in turn.expected_tools:
                if call.name == "propose_actions":
                    ActionBatch.model_validate(call.arguments)
    return hashlib.sha256(raw).hexdigest(), cases

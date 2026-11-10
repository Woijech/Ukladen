"""Explicitly approved, bounded real-model checks over synthetic fixtures only."""

import argparse
import json
import os
from decimal import Decimal
from pathlib import Path
from threading import Lock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.integrations.llm.openrouter import openrouter_model
from app.modules.ai.application.connections import ModelOffering
from app.modules.ai.application.streaming import stream_sink
from app.modules.ai.infrastructure.connections import Catalog, CatalogEntry
from evaluations.runtime import observe, score
from evaluations.scenarios import load_suite


class LiveConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: Literal["openrouter"]
    model: str = Field(min_length=3)
    approval_reference: str = Field(min_length=10)
    case_ids: tuple[str, ...] = Field(min_length=1, max_length=60)
    max_requests: int = Field(ge=1, le=240, strict=True)
    max_input_bytes: int = Field(ge=1024, le=65536, strict=True)
    max_output_tokens: int = Field(ge=16, le=2048, strict=True)
    input_usd_per_million: Decimal = Field(ge=0, allow_inf_nan=False)
    output_usd_per_million: Decimal = Field(ge=0, allow_inf_nan=False)
    max_cost_usd: Decimal = Field(gt=0, allow_inf_nan=False)
    streaming: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def bounded_selection(self):
        if len(set(self.case_ids)) != len(self.case_ids):
            raise ValueError("Select each case only once.")
        Catalog(
            entries=(CatalogEntry(id="evaluation", version=1, name="Evaluation", model=self.model),)
        )
        return self

    @property
    def request_reservation(self) -> Decimal:
        # Conservative byte-level token bound; route ceilings also disallow per-request fees.
        return (
            self.max_input_bytes * self.input_usd_per_million
            + self.max_output_tokens * self.output_usd_per_million
        ) / 1_000_000


class LiveBudget:
    def __init__(self, config: LiveConfig):
        self.config, self.requests, self.reserved = config, 0, Decimal(0)
        self.retry_after: int | None = None
        self.lock = Lock()

    def block(self, seconds: int) -> None:
        with self.lock:
            self.retry_after = seconds

    def admit(self) -> None:
        with self.lock:
            reservation = self.config.request_reservation
            if (
                self.requests >= self.config.max_requests
                or self.reserved + reservation > self.config.max_cost_usd
                or self.retry_after is not None
            ):
                raise RuntimeError("Live evaluation budget exhausted; no dispatch authorized.")
            self.requests += 1
            self.reserved += reservation


def execute(config: LiveConfig, *, transport=None) -> dict:
    digest, suite = load_suite()
    by_id = {case.id: case for case in suite}
    if any(identifier not in by_id for identifier in config.case_ids):
        raise ValueError("Unknown evaluation case.")
    # Only this dedicated variable is read; application catalogs/credentials are never loaded.
    budget = LiveBudget(config)
    records = []
    profile = ModelOffering(
        id="evaluation",
        version=1,
        name="Explicit evaluation",
        model=config.model,
        tools=True,
        streaming=config.streaming,
        max_input_bytes=config.max_input_bytes,
        max_output_tokens=config.max_output_tokens,
    )

    def credential() -> str:
        budget.admit()
        key = os.environ.get("UKLADEN_EVAL_API_KEY", "")
        if not key:
            raise ValueError("Set the dedicated UKLADEN_EVAL_API_KEY only for approved execution.")
        return key

    for identifier in config.case_ids:
        if (
            budget.requests >= config.max_requests
            or budget.reserved + config.request_reservation > config.max_cost_usd
            or budget.retry_after is not None
        ):
            break
        model, client = openrouter_model(profile, credential, budget.block, transport=transport)
        assert model.openrouter_provider is not None
        model.openrouter_provider["max_price"] = {
            "prompt": str(config.input_usd_per_million),
            "completion": str(config.output_usd_per_million),
            "request": "0",
        }
        token = stream_sink.set(lambda _: None) if config.streaming else None
        try:
            with client:
                cases, record = observe(by_id[identifier], model)
        finally:
            if token is not None:
                stream_sink.reset(token)
        record["turns"] = score(cases)
        record["observations"] = [
            {
                "name": case.name,
                "answer": case.actual_output,
                "tool_calls": [tool.model_dump(mode="json") for tool in case.tools_called or []],
            }
            for case in cases
        ]
        records.append(record)
    return {
        "mode": "live_synthetic_fixtures",
        "model_quality_gate": "requires_semantic_and_safety_review",
        "fixture_sha256": digest,
        "configuration": config.model_dump(mode="json"),
        "provider_requests_reserved": budget.requests,
        "cost_usd_reserved_upper_bound": str(budget.reserved),
        "provider_retry_after_seconds": budget.retry_after,
        "all_selected_cases_executed": len(records) == len(config.case_ids),
        "cases": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--execute", action="store_true", help="Requires separate bounded owner approval"
    )
    args = parser.parse_args()
    config = LiveConfig.model_validate_json(args.config.read_bytes())
    _, suite = load_suite()
    if set(config.case_ids) - {case.id for case in suite}:
        parser.error("Unknown evaluation case.")
    if not args.execute:
        print(
            json.dumps(
                {
                    "mode": "dry_run",
                    "provider_requests": 0,
                    "maximum_requests": config.max_requests,
                    "maximum_cost_usd": str(config.max_cost_usd),
                    "worst_case_reservation_per_request_usd": str(config.request_reservation),
                },
                indent=2,
            )
        )
        return 0
    if args.output is None or "UKLADEN_EVAL_API_KEY" not in os.environ:
        parser.error("Execution requires --output and the dedicated UKLADEN_EVAL_API_KEY.")
    # Refuse overwrites and keep synthetic transcripts private; do this before spending.
    descriptor = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w") as output:
        report = execute(config)
        json.dump(report, output, ensure_ascii=False, indent=2)
        output.write("\n")
    return int(
        not report["all_selected_cases_executed"]
        or any(not turn["passed"] for case in report["cases"] for turn in case["turns"])
    )


if __name__ == "__main__":
    raise SystemExit(main())

"""Objective fixture metrics, not semantic truth judgments about arbitrary prose."""

import re
from collections.abc import Callable, Sequence
from typing import Any

from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase


def recall_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
    if k < 1 or not relevant:
        raise ValueError("Recall requires positive k and labeled relevant sources.")
    return len(set(retrieved[:k]) & relevant) / len(relevant)


def reciprocal_rank(retrieved: Sequence[str], relevant: set[str]) -> float:
    if not relevant:
        raise ValueError("MRR requires labeled relevant sources.")
    return next((1 / rank for rank, item in enumerate(retrieved, 1) if item in relevant), 0.0)


def citation_precision(answer: str, available: set[str], required: set[str]) -> float:
    cited = set(re.findall(r"\[source:([^\]\s]+)\]", answer))
    if not cited:
        return float(not required)
    if not required <= cited:
        return 0.0
    return len(cited & available) / len(cited)


def tool_scores(case: LLMTestCase) -> dict[str, float]:
    actual, expected = case.tools_called or [], case.expected_tools or []
    actual_names, expected_names = [t.name for t in actual], [t.name for t in expected]
    allowed = set((case.metadata or {})["allowed_tools"])
    matching = sum(a == e for a, e in zip(actual, expected, strict=False))
    return {
        "tool_correctness": float(set(actual_names) == set(expected_names)),
        "tool_selection_accuracy": float(set(actual_names) <= allowed),
        "tool_arguments_correctness": matching / max(len(actual), len(expected), 1)
        if actual or expected
        else 1.0,
        "tool_call_sequence": float(actual_names == expected_names),
    }


def fixture_scores(case: LLMTestCase) -> dict[str, float]:
    data: dict[str, Any] = case.metadata or {}
    answer = case.actual_output or ""
    expected = data["required_facts"]
    # Exact, authored fact assertions are intentionally stricter than semantic equivalence.
    fact_recall = sum(fact in answer for fact in expected) / len(expected) if expected else 1.0
    claims = [c.strip() for c in re.sub(r"\[source:[^\]]+\]", "", answer).splitlines() if c.strip()]
    supported = data["supported_claims"]
    precision = sum(c in supported for c in claims) / len(claims) if claims else float(not expected)
    contexts = case.retrieval_context or []
    if any(not isinstance(context, str) for context in contexts):
        raise ValueError("These fixture metrics require string evidence envelopes.")
    contexts = [context for context in contexts if isinstance(context, str)]
    relevant = data["relevant_context"]
    scores = tool_scores(case) | {
        "task_completion": float(data["status"] == data["expected_status"]) * fact_recall,
        "faithfulness_exact_claims": precision,
        "answer_relevancy_exact_facts": fact_recall,
        "unsupported_claims_absent": float(all(c in supported for c in claims)),
        "citation_correctness": citation_precision(
            answer, set(data["available_sources"]), set(data["required_citations"])
        ),
        "forbidden_content_absent": float(not any(s in answer for s in data["forbidden_content"])),
        "hitl_enforcement": float(
            data["expected_status"] != "interrupted" or data["review_present"]
        ),
    }
    if relevant:
        scores |= {
            "contextual_relevancy_labeled": len(set(contexts) & set(relevant)) / len(set(contexts))
            if contexts
            else 0.0,
            "contextual_recall_labeled": recall_at_k(
                contexts, set(relevant), max(len(contexts), 1)
            ),
        }
    return scores


class ObjectiveMetric(BaseMetric):
    """DeepEval metric for a deterministic assertion over an actual runtime observation."""

    def __init__(self, name: str, scorer: Callable[[LLMTestCase], float]) -> None:
        self.name, self.scorer = name, scorer
        self.threshold, self.async_mode, self.verbose_mode = 1.0, False, False
        self.evaluation_model = "deterministic; no judge"

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        self.score = float(self.scorer(test_case))
        self.success = self.score >= 1.0
        self.reason = (
            "Objective fixture assertion passed" if self.success else self.name + " failed"
        )
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case)

    @property
    def __name__(self) -> Any:
        return self.name

"""Prepare and score manually reviewed synthetic AI-09 results; never calls a provider."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

SUITE = Path(__file__).resolve().parents[1] / "tests/fixtures/ai/ai-09.json"


def load_suite(path: Path = SUITE) -> tuple[str, list[dict]]:
    raw = path.read_bytes()
    suite = json.loads(raw)
    cases = suite["cases"]
    if suite["schema_version"] != "ai09-suite/v1" or len(cases) != 40:
        raise ValueError("Expected the versioned 40-case AI-09 suite.")
    if len({case["id"] for case in cases}) != 40:
        raise ValueError("Duplicate acceptance case IDs.")
    if Counter((case["split"], case["language"]) for case in cases) != {
        ("development", "ru"): 14,
        ("development", "en"): 6,
        ("held_out", "ru"): 14,
        ("held_out", "en"): 6,
    }:
        raise ValueError("Expected balanced 20/20 splits and 28 Russian/12 English cases.")
    for case in cases:
        if type(case["critical"]) is not bool or any(
            not case[field] for field in ("prompt", "setup", "expected", "forbidden")
        ):
            raise ValueError("Every case needs a prompt, setup and explicit acceptance rubric.")
    return hashlib.sha256(raw).hexdigest(), cases


def template(digest: str, cases: list[dict]) -> dict:
    return {
        "schema_version": "ai09-review/v1",
        "fixture_sha256": digest,
        "mode": "offline",
        "provider": None,
        "model": None,
        "reviewer": None,
        "approval_reference": None,
        "cases": [
            {
                "id": case["id"],
                "decision": "unreviewed",
                "observed": "",
                "notes": "",
                "critical_failures": [],
                "attempts": 0,
                "input_tokens": None,
                "output_tokens": None,
            }
            for case in cases
        ],
    }


def evaluate(digest: str, cases: list[dict], review: dict) -> dict:
    if (
        review["schema_version"] != "ai09-review/v1"
        or review["fixture_sha256"] != digest
        or review["mode"] not in ("offline", "live")
    ):
        raise ValueError("Review schema, fixture hash or mode does not match.")
    records = review["cases"]
    by_id = {record["id"]: record for record in records}
    if len(by_id) != len(records) or set(by_id) != {case["id"] for case in cases}:
        raise ValueError("Provide exactly one review record for every case, with no unknown IDs.")
    live = review["mode"] == "live"
    if live and (
        review["provider"] != "openrouter"
        or any(
            not isinstance(review[field], str) or not review[field].strip()
            for field in ("model", "reviewer", "approval_reference")
        )
    ):
        raise ValueError(
            "Live review needs OpenRouter, exact model, reviewer and approval reference."
        )
    passed, reviewed, attempts, critical = 0, 0, 0, []
    splits = {name: {"passed": 0, "reviewed": 0} for name in ("development", "held_out")}
    for case in cases:
        record = by_id[case["id"]]
        decision = record["decision"]
        if decision not in ("pass", "fail", "unreviewed"):
            raise ValueError("Invalid review decision.")
        if not isinstance(record["critical_failures"], list) or any(
            not isinstance(item, str) or not item.strip() for item in record["critical_failures"]
        ):
            raise ValueError("Critical failures must be a list of nonempty descriptions.")
        for field in ("attempts", "input_tokens", "output_tokens"):
            value = record[field]
            if value is None and field != "attempts":
                continue
            if type(value) is not int or value < 0:
                raise ValueError("Attempts and known usage must be nonnegative integers.")
        attempts += record["attempts"]
        if decision != "unreviewed":
            if any(
                not isinstance(record[field], str) or not record[field].strip()
                for field in ("observed", "notes")
            ):
                raise ValueError("Reviewed cases require observed evidence and reviewer notes.")
            reviewed += 1
            splits[case["split"]]["reviewed"] += 1
        if record["critical_failures"] or (case["critical"] and decision == "fail"):
            critical.append(case["id"])
        if decision == "pass":
            passed += 1
            splits[case["split"]]["passed"] += 1
    accepted = live and reviewed == 40 and passed >= 36 and attempts > 0 and not critical
    return {
        "mode": review["mode"],
        "reviewed": reviewed,
        "passed": passed,
        "total": 40,
        "splits": splits,
        "provider_attempts": attempts,
        "critical_failures": critical,
        "quality_gate": "accepted" if accepted else "blocked" if live else "not_evaluated",
        "accepted": accepted,
        "limitation": "Human-review scores only; no provider calls or authenticity audit.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=SUITE)
    parser.add_argument("--results", type=Path, help="Score an existing human-review JSON file.")
    arguments = parser.parse_args()
    try:
        digest, cases = load_suite(arguments.suite)
        if arguments.results is None:
            output = template(digest, cases)
            code = 0
        else:
            output = evaluate(digest, cases, json.loads(arguments.results.read_text()))
            code = 0 if output["accepted"] else 2
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"Invalid AI-09 input: {type(error).__name__}.\n")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

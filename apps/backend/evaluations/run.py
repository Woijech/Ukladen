"""Run deterministic DeepEval metrics locally; no LLM judge, telemetry or uploads."""

import argparse
import json
import statistics
from pathlib import Path

from evaluations.runtime import observe, score
from evaluations.scenarios import load_suite


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    digest, scenarios = load_suite()
    records = []
    for scenario in scenarios:
        cases, record = observe(scenario)
        record["turns"] = score(cases)
        record["passed"] = all(turn["passed"] for turn in record["turns"])
        records.append(record)
    names = {name for record in records for turn in record["turns"] for name in turn["metrics"]}
    report = {
        "mode": "offline_scripted_runtime",
        "model_quality_gate": "not_evaluated",
        "fixture_sha256": digest,
        "scenarios": len(records),
        "passed": sum(record["passed"] for record in records),
        "provider_requests": 0,
        "tokens": None,
        "cost_usd": "0",
        "latency_median_ms": statistics.median(r["elapsed_ms"] for r in records),
        "metrics": {
            name: statistics.mean(
                t["metrics"][name] for r in records for t in r["turns"] if name in t["metrics"]
            )
            for name in sorted(names)
        },
        "cases": records,
    }
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, indent=2))
    return int(report["passed"] != report["scenarios"])


if __name__ == "__main__":
    raise SystemExit(main())

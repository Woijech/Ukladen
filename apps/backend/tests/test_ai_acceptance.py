from copy import deepcopy

import pytest

from benchmarks.ai_acceptance import evaluate, load_suite, template


def reviewed():
    digest, cases = load_suite()
    result = template(digest, cases)
    result.update(
        mode="live",
        provider="openrouter",
        model="synthetic/model-for-scorer-test",
        reviewer="Synthetic reviewer",
        approval_reference="Synthetic test record; no actual provider authorization",
    )
    for record in result["cases"]:
        record.update(
            decision="pass",
            observed="Synthetic observed output",
            notes="Rubric checked",
            attempts=1,
        )
    return digest, cases, result


def test_offline_and_unreviewed_results_never_pass_model_quality():
    digest, cases = load_suite()
    result = template(digest, cases)
    summary = evaluate(digest, cases, result)
    assert summary["quality_gate"] == "not_evaluated" and not summary["accepted"]
    assert summary["reviewed"] == summary["passed"] == summary["provider_attempts"] == 0
    _, _, result = reviewed()
    result["mode"] = "offline"
    assert not evaluate(digest, cases, result)["accepted"]
    result["mode"] = "live"
    result["cases"][0]["decision"] = "unreviewed"
    summary = evaluate(digest, cases, result)
    assert summary["passed"] == 39 and not summary["accepted"]


def test_quality_threshold_and_critical_failure_override():
    digest, cases, result = reviewed()
    ordinary = [case["id"] for case in cases if not case["critical"]]
    for record in result["cases"]:
        if record["id"] in ordinary[:4]:
            record["decision"] = "fail"
    summary = evaluate(digest, cases, result)
    assert summary["passed"] == 36 and summary["accepted"]
    result["cases"][0]["critical_failures"] = ["Unconfirmed business-content write"]
    assert not evaluate(digest, cases, result)["accepted"]
    result["cases"][0]["critical_failures"] = []
    critical = next(case["id"] for case in cases if case["critical"])
    next(record for record in result["cases"] if record["id"] == critical)["decision"] = "fail"
    summary = evaluate(digest, cases, result)
    assert critical in summary["critical_failures"] and not summary["accepted"]
    _, _, result = reviewed()
    for record in result["cases"]:
        if record["id"] in ordinary[:5]:
            record["decision"] = "fail"
    assert not evaluate(digest, cases, result)["accepted"]


@pytest.mark.parametrize(
    "change",
    [
        lambda result: result.update(fixture_sha256="wrong"),
        lambda result: result.update(mode="fake-as-live"),
        lambda result: result.update(provider="other-real-provider"),
        lambda result: result.update(model=""),
        lambda result: result.update(reviewer=None),
        lambda result: result.update(approval_reference=""),
        lambda result: result["cases"].pop(),
        lambda result: result["cases"].append(deepcopy(result["cases"][0])),
        lambda result: result["cases"][0].update(id="unknown"),
        lambda result: result["cases"][0].update(decision="skipped"),
        lambda result: result["cases"][0].update(observed=""),
        lambda result: result["cases"][0].update(notes=""),
        lambda result: result["cases"][0].update(attempts=True),
        lambda result: result["cases"][0].update(input_tokens=-1),
        lambda result: result["cases"][0].update(output_tokens=1.5),
        lambda result: result["cases"][0].update(critical_failures="none"),
        lambda result: result["cases"][0].update(critical_failures=[""]),
    ],
)
def test_invalid_review_cannot_be_scored_as_success(change):
    digest, cases, result = reviewed()
    change(result)
    with pytest.raises(ValueError):
        evaluate(digest, cases, result)


def test_unknown_usage_stays_unknown_and_zero_attempts_cannot_pass():
    digest, cases, result = reviewed()
    assert all(record["input_tokens"] is None for record in result["cases"])
    assert evaluate(digest, cases, result)["accepted"]
    for record in result["cases"]:
        record["attempts"] = 0
    assert not evaluate(digest, cases, result)["accepted"]

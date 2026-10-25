import math
import sys
from threading import Event, Thread
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.search.application.embeddings import EmbeddingUnavailable
from benchmarks import embedding_runtime as proof


def test_measurement_summary_rejects_empty_and_uses_nearest_rank_p95() -> None:
    with pytest.raises(ValueError):
        proof.summary([])
    result = proof.summary([index / 1000 for index in range(1, 21)])
    assert result == pytest.approx({"count": 20, "p50_ms": 10.5, "p95_ms": 19, "max_ms": 20})


def test_proof_api_offloads_model_and_reports_failures(monkeypatch, tmp_path) -> None:
    entered, release = Event(), Event()
    model = SimpleNamespace(_runtime=None)

    def embed(texts, *, purpose):
        assert purpose == "query" and len(texts) == 1
        entered.set()
        assert release.wait(5)
        return [(1.0, 0.0)]

    model.embed = embed
    monkeypatch.setattr(proof, "E5EmbeddingProvider", lambda directory: model)
    monkeypatch.setitem(sys.modules, "app.main", SimpleNamespace(create_app=FastAPI))
    apps = []
    monkeypatch.setattr(proof.uvicorn, "run", lambda app, **kwargs: apps.append(app))
    proof.serve(tmp_path, "api", 8000)
    with TestClient(apps[0]) as client:
        responses = []
        thread = Thread(target=lambda: responses.append(client.post("/_proof/embed")))
        thread.start()
        try:
            assert entered.wait(5)
            assert client.get("/_proof/state").status_code == 200
        finally:
            release.set()
            thread.join(5)
        assert not thread.is_alive()
        assert responses[0].json()["norm"] == 1

        def failed(*args, **kwargs):
            raise EmbeddingUnavailable("Private diagnostic")

        model.embed = failed
        response = client.post("/_proof/embed")
        assert response.status_code == 503 and "Private" not in response.text


def test_worker_is_single_start_and_stops_with_recorded_throughput(monkeypatch, tmp_path) -> None:
    entered = Event()

    def embed(texts, *, purpose):
        assert purpose == "document" and len(texts) == 4
        entered.set()
        return [(1.0, 0.0)] * 4

    model = SimpleNamespace(_runtime=True, embed=embed)
    monkeypatch.setattr(proof, "E5EmbeddingProvider", lambda directory: model)
    apps = []
    monkeypatch.setattr(proof.uvicorn, "run", lambda app, **kwargs: apps.append(app))
    proof.serve(tmp_path, "worker", 8000)
    with TestClient(apps[0]) as client:
        assert client.post("/_proof/start").status_code == 200
        assert entered.wait(5)
        assert client.post("/_proof/start").status_code == 409
        result = client.post("/_proof/stop").json()
        assert result["batches"] > 0 and result["seconds"] > 0
        assert not result["running"] and not result["error"]
        assert math.isfinite(4 * result["batches"] / result["seconds"])

"""AI-05 CPU proof. No real providers, credentials or user content are used."""

import argparse
import json
import math
import os
import platform
import statistics
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from threading import Event, Thread
from time import monotonic, sleep

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from starlette.concurrency import run_in_threadpool

from app.integrations.embeddings.e5 import E5EmbeddingProvider
from app.modules.search.application.embeddings import EmbeddingUnavailable, InvalidEmbeddingInput

DOCUMENTS = (
    "Нормализация реляционных баз данных устраняет избыточность и аномалии обновления. "
    "Нормальные формы определяются функциональными зависимостями атрибутов.",
    "Закон Ньютона связывает силу, массу и ускорение. При постоянной массе ускорение "
    "пропорционально приложенной силе.",
    "Фотосинтез происходит в хлоропластах растений. Энергия солнечного света превращается "
    "в химическую энергию, выделяется кислород.",
    "Breadth-first search traverses a graph using a queue. It finds shortest paths "
    "in an unweighted graph by visiting vertices level by level.",
    "Рецепт яблочного пирога: смешать муку, яйца и сахар, добавить яблоки и выпекать в духовке.",
    "A personal budget tracks income and expenses. "
    "Set aside savings before discretionary spending.",
)
QUERIES = (
    ("Как избавиться от повторяющихся данных и аномалий в таблицах?", 0),
    ("How do functional dependencies help organize database tables?", 0),
    ("Как зависит ускорение тела от приложенной силы?", 1),
    ("What connects force and acceleration?", 1),
    ("Как растения используют свет для получения энергии?", 2),
    ("Where do plants produce oxygen using sunlight?", 2),
    ("Как найти кратчайший путь в графе без весов с помощью очереди?", 3),
    ("Which traversal visits neighboring vertices level by level?", 3),
    ("Что приготовить из яблок, муки и яиц?", 4),
    ("How can I bake an apple dessert?", 4),
    ("Как учитывать доходы, расходы и откладывать деньги?", 5),
    ("How do I plan spending and savings?", 5),
)
# Synthetic indexing load includes longer documents, not only short smoke examples.
INDEX_BATCH = tuple(DOCUMENTS[index] * 8 for index in range(4))


def summary(samples: list[float]) -> dict[str, float | int]:
    if not samples:
        raise ValueError("No successful measurement samples.")
    ordered = sorted(samples)
    return {
        "count": len(samples),
        "p50_ms": statistics.median(samples) * 1000,
        "p95_ms": ordered[math.ceil(len(samples) * 0.95) - 1] * 1000,
        "max_ms": ordered[-1] * 1000,
    }


def process_memory() -> dict[str, int]:
    lines = Path("/proc/self/status").read_text().splitlines()
    return {
        line.split(":")[0] + "_kib": int(line.split()[1])
        for line in lines
        if line.startswith(("VmRSS:", "VmHWM:", "VmSwap:"))
    }


def system_sample() -> dict:
    memory = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value, *_ = line.split()
        if key in ("MemTotal:", "MemAvailable:", "SwapTotal:", "SwapFree:"):
            memory[key.removesuffix(":") + "_kib"] = int(value)
    vm = dict(line.split() for line in Path("/proc/vmstat").read_text().splitlines())
    cpu = [int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:9]]
    return {
        **memory,
        "swap_in_pages": int(vm["pswpin"]),
        "swap_out_pages": int(vm["pswpout"]),
        "cpu_ticks": cpu,
        "load_average": list(os.getloadavg()),
    }


def serve(directory: Path, role: str, port: int) -> None:
    if role == "api":
        from app.main import create_app

        application = create_app()
    else:
        application = FastAPI()
    provider = E5EmbeddingProvider(directory)
    stop = Event()
    state = {"batches": 0, "seconds": 0.0, "error": False}
    thread: Thread | None = None
    query_index = 0

    def index() -> None:
        deadline = monotonic() + 150
        try:
            while not stop.is_set() and monotonic() < deadline:
                before = monotonic()
                provider.embed(INDEX_BATCH, purpose="document")
                state["seconds"] += monotonic() - before
                state["batches"] += 1
        except Exception:
            state["error"] = True

    @application.get("/_proof/state")
    def status() -> dict:
        return {
            **state,
            "pid": os.getpid(),
            "memory": process_memory(),
            "loaded": provider._runtime is not None,
            "running": thread is not None and thread.is_alive(),
        }

    @application.post("/_proof/embed")
    async def embed() -> dict:
        nonlocal query_index
        texts = [QUERIES[query_index % len(QUERIES)][0]] if role == "api" else INDEX_BATCH
        query_index += 1
        before = monotonic()
        try:
            vectors = await run_in_threadpool(
                provider.embed, texts, purpose="query" if role == "api" else "document"
            )
        except EmbeddingUnavailable:
            raise HTTPException(503, "Synthetic embedding proof failed.") from None
        return {
            "seconds": monotonic() - before,
            "dimensions": len(vectors[0]),
            "norm": math.hypot(*vectors[0]),
            "memory": process_memory(),
        }

    if role == "worker":

        @application.post("/_proof/start")
        def start() -> dict:
            nonlocal thread
            if thread is not None:
                raise HTTPException(409, "Indexing proof already started.")
            thread = Thread(target=index, daemon=True)
            thread.start()
            return {"started": True}

        @application.post("/_proof/stop")
        def finish() -> dict:
            stop.set()
            if thread is not None:
                thread.join(timeout=30)
                if thread.is_alive():
                    raise HTTPException(503, "Indexing proof did not stop.")
            return status()

    uvicorn.run(application, host="0.0.0.0", port=port, access_log=False)


def quality(directory: Path) -> dict:
    provider = E5EmbeddingProvider(directory)
    before = monotonic()
    documents = []
    for offset in range(0, len(DOCUMENTS), 4):
        documents.extend(provider.embed(DOCUMENTS[offset : offset + 4], purpose="document"))
    ranks = []
    for query, expected in QUERIES:
        vector = provider.embed([query], purpose="query")[0]
        scores = [sum(a * b for a, b in zip(vector, doc, strict=True)) for doc in documents]
        ordered = sorted(range(len(scores)), key=lambda index: (-scores[index], index))
        ranks.append(ordered.index(expected) + 1)
    tokenizer, _ = provider._load()
    count = 1
    while len(tokenizer.encode("query: " + "word " * count).ids) < 512:
        count += 1
    boundary = "word " * count
    assert len(tokenizer.encode("query: " + boundary).ids) == 512
    start = monotonic()
    provider.embed([boundary], purpose="query")
    boundary_query_ms = (monotonic() - start) * 1000
    oversized = boundary + " word word"
    assert len(tokenizer.encode("query: " + oversized).ids) > 512
    try:
        provider.embed([oversized], purpose="query")
    except InvalidEmbeddingInput:
        pass
    else:
        raise AssertionError("Oversized real-tokenizer input was not rejected.")
    return {
        "profile": asdict(provider.profile),
        "cases": len(ranks),
        "top1": ranks.count(1),
        "ranks": ranks,
        "seconds": monotonic() - before,
        "memory": process_memory(),
        "packages": {name: version(name) for name in ("onnxruntime", "tokenizers", "numpy")},
        "query_tokens": [len(tokenizer.encode("query: " + query).ids) for query, _ in QUERIES],
        "index_tokens": [len(tokenizer.encode("passage: " + text).ids) for text in INDEX_BATCH],
        "boundary_query_tokens": 512,
        "boundary_query_ms": boundary_query_ms,
        "oversized_rejected": True,
    }


def measure(api: str, worker: str, duration: int, query_interval_ms: int = 100) -> dict:
    def request(client: httpx.Client, method: str, path: str) -> dict:
        response = client.request(method, path)
        response.raise_for_status()
        return response.json()

    def phase() -> dict:
        samples: dict[str, list[float]] = {"live": [], "ready": []}
        start = monotonic()
        first = system_sample()
        observations = [first]
        with httpx.Client(base_url=api, timeout=30, trust_env=False) as client:
            while monotonic() - start < duration:
                for name in samples:
                    before = monotonic()
                    request(client, "GET", f"/api/health/{name}")
                    samples[name].append(monotonic() - before)
                observations.append(system_sample())
                sleep(0.05)
        last = observations[-1]
        deltas = [b - a for a, b in zip(first["cpu_ticks"], last["cpu_ticks"], strict=True)]
        return {
            "api": {name: summary(values) for name, values in samples.items()},
            "system_before": first,
            "system_after": last,
            "min_available_kib": min(item["MemAvailable_kib"] for item in observations),
            "max_used_swap_kib": max(
                item["SwapTotal_kib"] - item["SwapFree_kib"] for item in observations
            ),
            "swap_in_pages": last["swap_in_pages"] - first["swap_in_pages"],
            "swap_out_pages": last["swap_out_pages"] - first["swap_out_pages"],
            "cpu_busy_percent": 100 * (1 - (deltas[3] + deltas[4]) / max(sum(deltas), 1)),
        }

    with (
        httpx.Client(base_url=api, timeout=60, trust_env=False) as client,
        httpx.Client(base_url=worker, timeout=60, trust_env=False) as index_client,
    ):
        initial = request(client, "GET", "/_proof/state")
        worker_initial = request(index_client, "GET", "/_proof/state")
        if initial["loaded"] or worker_initial["loaded"]:
            raise ValueError("Restart proof processes for reproducible cold measurements.")
        baseline = phase()
        cold_query = request(client, "POST", "/_proof/embed")
        cold_batch = request(index_client, "POST", "/_proof/embed")
        queries: list[float] = []
        stop = Event()

        def query_load() -> None:
            with httpx.Client(base_url=api, timeout=30, trust_env=False) as caller:
                while not stop.is_set():
                    before = monotonic()
                    request(caller, "POST", "/_proof/embed")
                    queries.append(monotonic() - before)
                    stop.wait(query_interval_ms / 1000)

        request(index_client, "POST", "/_proof/start")
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(query_load)
                try:
                    loaded = phase()
                finally:
                    stop.set()
                future.result(timeout=30)
        finally:
            worker_state = request(index_client, "POST", "/_proof/stop")
        if worker_state["error"] or not worker_state["batches"]:
            raise ValueError("Indexing worker failed or produced no batches.")
        degradation = {
            name: (loaded["api"][name]["p95_ms"] / baseline["api"][name]["p95_ms"] - 1) * 100
            for name in ("live", "ready")
        }
        return {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "duration_per_phase_seconds": duration,
            "query_interval_ms": query_interval_ms,
            "baseline": baseline,
            "loaded": loaded,
            "cold_query": cold_query,
            "cold_index_batch": cold_batch,
            "warm_query": summary(queries),
            "api_degradation_percent": degradation,
            "api_process": request(client, "GET", "/_proof/state"),
            "worker_process": worker_state,
            "index_documents_per_second": 4 * worker_state["batches"] / worker_state["seconds"],
            "latency_targets_met": summary(queries)["p95_ms"] <= 1000
            and all(value <= 20 for value in degradation.values()),
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    server = commands.add_parser("serve")
    server.add_argument("directory", type=Path)
    server.add_argument("--role", choices=("api", "worker"), required=True)
    server.add_argument("--port", type=int, default=8000)
    check = commands.add_parser("quality")
    check.add_argument("directory", type=Path)
    benchmark = commands.add_parser("measure")
    benchmark.add_argument("--api", default="http://127.0.0.1:58400")
    benchmark.add_argument("--worker", default="http://127.0.0.1:58401")
    benchmark.add_argument("--duration", type=int, choices=range(10, 121), default=30)
    benchmark.add_argument("--query-interval-ms", type=int, choices=range(1001), default=100)
    arguments = parser.parse_args()
    if arguments.command == "serve":
        serve(arguments.directory, arguments.role, arguments.port)
    elif arguments.command == "quality":
        print(json.dumps(quality(arguments.directory), indent=2))
    else:
        print(
            json.dumps(
                measure(
                    arguments.api, arguments.worker, arguments.duration, arguments.query_interval_ms
                ),
                indent=2,
            )
        )

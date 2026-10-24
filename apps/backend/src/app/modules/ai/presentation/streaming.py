import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from queue import Empty, Full, Queue
from threading import BoundedSemaphore, Event
from typing import Any

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from app.modules.ai.application.agent import AgentInput
from app.modules.ai.application.lifecycle import AiService
from app.modules.ai.application.streaming import stream_sink
from app.modules.ai.domain.state import Run
from app.modules.ai.presentation.schemas import RunResponse

_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="ai-stream")
_slots = BoundedSemaphore(8)


def frame(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def stream_response(
    service: AiService, run: Run, request: AgentInput, created: bool
) -> StreamingResponse:
    events: Queue[dict[str, Any]] = Queue(maxsize=128)
    closed = Event()

    def publish(event: dict[str, Any]) -> None:
        if not closed.is_set():
            try:
                events.put_nowait(event)
            except Full:
                # shortcut: slow consumers recover canonical state, transient text is not replayed.
                closed.set()

    def execute() -> None:
        token = stream_sink.set(publish)
        try:
            service.execute(run, request)
        finally:
            stream_sink.reset(token)
            _slots.release()

    if created:
        if not _slots.acquire(blocking=False):
            service.cancel(run.user_id, run.id)
            raise HTTPException(503, "AI streaming capacity is unavailable.")
        try:
            future = _executor.submit(copy_context().run, execute)
        except BaseException:
            _slots.release()
            service.cancel(run.user_id, run.id)
            raise
    else:
        future = None

    def body() -> Iterator[str]:
        try:
            yield frame(
                "run",
                RunResponse.from_snapshot(service.get_run(run.user_id, run.id)).model_dump(
                    mode="json"
                ),
            )
            while future is not None and (not future.done() or not events.empty()):
                if closed.is_set():
                    yield frame("recover", {"run_id": str(run.id)})
                    return
                try:
                    item = events.get(timeout=0.5)
                except Empty:
                    yield ": keepalive\n\n"
                    continue
                # Cancellation/deletion/expiry fence late provider fragments as well as commits.
                snapshot = service.get_run(run.user_id, run.id)
                if snapshot.run.status in {"cancelled", "failed"}:
                    break
                yield frame(item["event"], item["data"])
            yield frame(
                "run",
                RunResponse.from_snapshot(service.get_run(run.user_id, run.id)).model_dump(
                    mode="json"
                ),
            )
            yield frame("done", {})
        except Exception:
            yield frame("recover", {"run_id": str(run.id)})
        finally:
            closed.set()

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store, no-transform",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )

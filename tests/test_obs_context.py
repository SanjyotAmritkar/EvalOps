"""Correlation context: bind / reset, dispatch snapshot, and no cross-leak
between concurrent asyncio tasks and threads."""

from __future__ import annotations

import asyncio
import threading

from evalops.obs.context import (
    bind,
    correlation_scope,
    get_context,
    get_field,
    reset,
    snapshot_for_dispatch,
)


def test_bind_merges_and_reset_restores() -> None:
    assert get_context() == {}
    token = bind(request_id="r1", experiment_id="e1")
    assert get_context() == {"request_id": "r1", "experiment_id": "e1"}

    inner = bind(job_id="j1", experiment_id="e2")
    assert get_context() == {"request_id": "r1", "experiment_id": "e2", "job_id": "j1"}
    reset(inner)
    assert get_context() == {"request_id": "r1", "experiment_id": "e1"}
    reset(token)
    assert get_context() == {}


def test_bind_drops_none_and_stringifies() -> None:
    with correlation_scope(request_id="r", job_id=None, experiment_id=123):  # type: ignore[arg-type]
        assert get_field("job_id") is None
        assert get_field("experiment_id") == "123"  # non-str coerced
    assert get_context() == {}


def test_scope_restores_even_on_exception() -> None:
    try:
        with correlation_scope(request_id="boom"):
            raise RuntimeError("x")
    except RuntimeError:
        pass
    assert get_context() == {}


def test_snapshot_for_dispatch_is_only_request_and_experiment() -> None:
    with correlation_scope(
        request_id="r", experiment_id="e", job_id="j", celery_task_id="t", project_id="p"
    ):
        assert snapshot_for_dispatch() == {"request_id": "r", "experiment_id": "e"}


def test_concurrent_async_tasks_do_not_leak() -> None:
    seen: dict[str, str | None] = {}

    async def worker(name: str) -> None:
        with correlation_scope(request_id=name):
            await asyncio.sleep(0.01)
            seen[name] = get_field("request_id")

    async def main() -> None:
        await asyncio.gather(*(worker(f"req-{i}") for i in range(20)))

    asyncio.run(main())
    assert seen == {f"req-{i}": f"req-{i}" for i in range(20)}


def test_concurrent_threads_do_not_leak() -> None:
    seen: dict[int, str | None] = {}
    barrier = threading.Barrier(10)

    def worker(i: int) -> None:
        with correlation_scope(request_id=f"t-{i}"):
            barrier.wait()
            seen[i] = get_field("request_id")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert seen == {i: f"t-{i}" for i in range(10)}
    assert get_context() == {}

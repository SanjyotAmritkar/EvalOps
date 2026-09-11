"""Celery application configuration (CP 10.4): delivery semantics and the
configurable time-limit safety net. See celery_app.py's module docstring for
the at-most-once rationale this locks in."""

from __future__ import annotations

import pytest

from evalops.worker.celery_app import (
    DEFAULT_SOFT_TIME_LIMIT_S,
    DEFAULT_TIME_LIMIT_S,
    broker_url,
    create_celery_app,
)


def test_broker_url_defaults_to_local_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    assert broker_url() == "redis://localhost:6379/0"


def test_broker_url_reads_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://redis:6379/0")
    assert broker_url() == "redis://redis:6379/0"


def test_delivery_semantics_are_at_most_once_by_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CELERY_TASK_SOFT_TIME_LIMIT_S", raising=False)
    monkeypatch.delenv("CELERY_TASK_TIME_LIMIT_S", raising=False)
    app = create_celery_app()

    # (B)/(C): never redeliver / re-execute an in-flight evaluation.
    assert app.conf.task_acks_late is False
    assert app.conf.task_reject_on_worker_lost is False

    # (A): broker reconnection stays on -- a different, safe category.
    assert app.conf.broker_connection_retry is True
    assert app.conf.broker_connection_retry_on_startup is True

    # Fair dispatch for long-running tasks; independent of ack semantics.
    assert app.conf.worker_prefetch_multiplier == 1

    # No result backend: PostgreSQL stays the sole authoritative record.
    assert app.conf.result_backend is None


def test_time_limits_default_to_a_generous_safety_net(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CELERY_TASK_SOFT_TIME_LIMIT_S", raising=False)
    monkeypatch.delenv("CELERY_TASK_TIME_LIMIT_S", raising=False)
    app = create_celery_app()
    assert app.conf.task_soft_time_limit == DEFAULT_SOFT_TIME_LIMIT_S
    assert app.conf.task_time_limit == DEFAULT_TIME_LIMIT_S
    assert app.conf.task_soft_time_limit < app.conf.task_time_limit


def test_time_limits_are_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CELERY_TASK_SOFT_TIME_LIMIT_S", "60")
    monkeypatch.setenv("CELERY_TASK_TIME_LIMIT_S", "90")
    app = create_celery_app()
    assert app.conf.task_soft_time_limit == 60.0
    assert app.conf.task_time_limit == 90.0


@pytest.mark.parametrize("raw", ["0", "", "not-a-number"])
def test_time_limit_env_falls_back_or_disables(raw: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CELERY_TASK_SOFT_TIME_LIMIT_S", raw)
    app = create_celery_app()
    if raw == "0":
        assert app.conf.task_soft_time_limit is None
    else:
        # blank / unparsable -> the documented default, never a crash
        assert app.conf.task_soft_time_limit == DEFAULT_SOFT_TIME_LIMIT_S

"""Tests for evalops.domain.entities.ReleasePolicy."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from evalops.domain.entities import ReleasePolicy
from evalops.domain.errors import DomainValidationError


def test_valid_policy_keeps_its_thresholds() -> None:
    policy = ReleasePolicy(
        name="default",
        thresholds={"quality": 0.02, "cost_usd": 0.10, "latency_p95_ms": 0.15},
        max_safety_violations=0,
    )

    assert policy.thresholds["latency_p95_ms"] == 0.15
    assert len(policy.id) == 32


def test_thresholds_are_read_only_and_do_not_alias_the_caller() -> None:
    supplied = {"quality": 0.02}
    policy = ReleasePolicy(name="default", thresholds=supplied)

    supplied["quality"] = 0.99

    assert policy.thresholds["quality"] == 0.02
    with pytest.raises(TypeError):
        policy.thresholds["quality"] = 0.99  # type: ignore[index]


def test_negative_threshold_value_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        ReleasePolicy(name="default", thresholds={"quality": -0.01})


def test_blank_threshold_metric_name_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        ReleasePolicy(name="default", thresholds={"   ": 0.1})


def test_negative_max_safety_violations_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        ReleasePolicy(name="default", max_safety_violations=-1)


def test_blank_name_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        ReleasePolicy(name="   ")


def test_is_immutable() -> None:
    policy = ReleasePolicy(name="default")

    with pytest.raises(FrozenInstanceError):
        policy.name = "other"  # type: ignore[misc]

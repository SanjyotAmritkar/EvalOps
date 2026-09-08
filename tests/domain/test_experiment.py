"""Tests for evalops.domain.entities.Experiment."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime
from typing import Any

import pytest

from evalops.domain.entities import Experiment
from evalops.domain.errors import DomainValidationError

VALID_KWARGS: dict[str, Any] = {
    "project_id": "proj-1",
    "dataset_id": "ds-1",
    "baseline_version_id": "sv-baseline",
    "candidate_version_id": "sv-candidate",
}


def test_valid_experiment_has_defaults() -> None:
    experiment = Experiment(**VALID_KWARGS)

    assert experiment.repeats == 1
    assert experiment.release_policy_id is None
    assert len(experiment.id) == 32
    assert experiment.created_at.tzinfo is not None


def test_baseline_and_candidate_must_differ() -> None:
    with pytest.raises(DomainValidationError):
        Experiment(
            project_id="proj-1",
            dataset_id="ds-1",
            baseline_version_id="sv-x",
            candidate_version_id="sv-x",
        )


def test_repeats_below_one_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        Experiment(**VALID_KWARGS, repeats=0)


@pytest.mark.parametrize(
    "field_name",
    ["project_id", "dataset_id", "baseline_version_id", "candidate_version_id"],
)
def test_blank_required_string_is_rejected(field_name: str) -> None:
    kwargs = {**VALID_KWARGS, field_name: "   "}

    with pytest.raises(DomainValidationError):
        Experiment(**kwargs)


def test_blank_release_policy_id_is_rejected_when_provided() -> None:
    with pytest.raises(DomainValidationError):
        Experiment(**VALID_KWARGS, release_policy_id="")


def test_naive_created_at_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        Experiment(**VALID_KWARGS, created_at=datetime(2024, 1, 1))


def test_is_immutable() -> None:
    experiment = Experiment(**VALID_KWARGS)

    with pytest.raises(FrozenInstanceError):
        experiment.repeats = 5  # type: ignore[misc]

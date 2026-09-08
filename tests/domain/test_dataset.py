"""Tests for evalops.domain.entities.Dataset."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime
from typing import Any

import pytest

from evalops.domain.entities import Dataset, DatasetCase
from evalops.domain.errors import DomainValidationError


def _case(case_id: str) -> DatasetCase:
    return DatasetCase(input=f"input for {case_id}", id=case_id)


def test_valid_dataset_holds_its_cases_as_a_tuple() -> None:
    case_a, case_b = _case("a"), _case("b")
    dataset = Dataset(project_id="proj-1", name="golden-set", version=1, cases=(case_a, case_b))

    assert isinstance(dataset.cases, tuple)
    assert dataset.cases == (case_a, case_b)
    assert dataset.created_at.tzinfo is not None


def test_empty_cases_are_rejected() -> None:
    with pytest.raises(DomainValidationError):
        Dataset(project_id="proj-1", name="d", version=1, cases=())


def test_duplicate_case_ids_are_rejected() -> None:
    with pytest.raises(DomainValidationError):
        Dataset(project_id="proj-1", name="d", version=1, cases=(_case("dup"), _case("dup")))


def test_version_below_one_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        Dataset(project_id="proj-1", name="d", version=0, cases=(_case("a"),))


@pytest.mark.parametrize("field_name", ["project_id", "name"])
def test_blank_required_string_is_rejected(field_name: str) -> None:
    kwargs: dict[str, Any] = {
        "project_id": "proj-1",
        "name": "d",
        "version": 1,
        "cases": (_case("a"),),
        field_name: "   ",
    }

    with pytest.raises(DomainValidationError):
        Dataset(**kwargs)


def test_naive_created_at_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        Dataset(
            project_id="proj-1",
            name="d",
            version=1,
            cases=(_case("a"),),
            created_at=datetime(2024, 1, 1),
        )


def test_is_immutable() -> None:
    dataset = Dataset(project_id="proj-1", name="d", version=1, cases=(_case("a"),))

    with pytest.raises(FrozenInstanceError):
        dataset.name = "other"  # type: ignore[misc]

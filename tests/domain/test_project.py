"""Tests for evalops.domain.entities.Project."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest

from evalops.domain.entities import Project
from evalops.domain.errors import DomainValidationError


def test_valid_project_gets_an_id_and_aware_timestamp() -> None:
    project = Project(name="Customer Support Agent")

    assert len(project.id) == 32
    assert project.created_at.tzinfo is not None


def test_blank_name_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        Project(name="   ")


def test_blank_explicit_id_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        Project(name="x", id="")


def test_naive_created_at_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        Project(name="x", created_at=datetime(2024, 1, 1))


def test_is_immutable() -> None:
    project = Project(name="x")

    with pytest.raises(FrozenInstanceError):
        project.name = "y"  # type: ignore[misc]

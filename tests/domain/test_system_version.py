"""Tests for evalops.domain.entities.SystemVersion."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime
from typing import Any

import pytest

from evalops.domain.entities import SystemVersion
from evalops.domain.enums import ProviderName
from evalops.domain.errors import DomainValidationError

VALID_KWARGS: dict[str, Any] = {
    "project_id": "proj-1",
    "name": "support-prompt",
    "version": "v1",
    "provider": ProviderName.OPENAI,
    "model": "gpt-4o-mini",
    "prompt_template": "Answer the question: {question}",
}


def test_valid_system_version_keeps_its_configuration() -> None:
    system_version = SystemVersion(**VALID_KWARGS, parameters={"temperature": 0.2})

    assert system_version.provider is ProviderName.OPENAI
    assert system_version.model == "gpt-4o-mini"
    assert system_version.parameters == {"temperature": 0.2}
    assert system_version.rag_config is None
    assert system_version.tool_policy is None
    assert len(system_version.id) == 32


@pytest.mark.parametrize(
    "field_name", ["project_id", "name", "version", "model", "prompt_template"]
)
def test_blank_required_string_is_rejected(field_name: str) -> None:
    kwargs = {**VALID_KWARGS, field_name: "   "}

    with pytest.raises(DomainValidationError):
        SystemVersion(**kwargs)


def test_parameters_do_not_alias_the_callers_dict() -> None:
    mutable = {"temperature": 0.7}
    system_version = SystemVersion(**VALID_KWARGS, parameters=mutable)

    mutable["temperature"] = 0.0

    assert system_version.parameters == {"temperature": 0.7}


def test_parameters_cannot_be_mutated_through_the_field() -> None:
    system_version = SystemVersion(**VALID_KWARGS, parameters={"temperature": 0.7})

    with pytest.raises(TypeError):
        system_version.parameters["temperature"] = 0.9  # type: ignore[index]


def test_rag_config_and_tool_policy_are_read_only_when_present() -> None:
    system_version = SystemVersion(
        **VALID_KWARGS,
        rag_config={"top_k": 5},
        tool_policy={"allow": ["search"]},
    )
    assert system_version.rag_config is not None
    assert system_version.tool_policy is not None

    with pytest.raises(TypeError):
        system_version.rag_config["top_k"] = 9  # type: ignore[index]
    with pytest.raises(TypeError):
        system_version.tool_policy["allow"] = []  # type: ignore[index]


def test_nested_values_are_not_deep_frozen() -> None:
    # Documented behaviour: the guarantee is shallow. A nested list stays mutable.
    system_version = SystemVersion(**VALID_KWARGS, parameters={"stop": ["\n"]})

    system_version.parameters["stop"].append("END")

    assert system_version.parameters["stop"] == ["\n", "END"]


@pytest.mark.parametrize("bad_provider", ["openai", 123])
def test_provider_must_be_a_providername_member(bad_provider: object) -> None:
    kwargs = {**VALID_KWARGS, "provider": bad_provider}

    with pytest.raises(DomainValidationError):
        SystemVersion(**kwargs)


def test_naive_created_at_is_rejected() -> None:
    with pytest.raises(DomainValidationError):
        SystemVersion(**VALID_KWARGS, created_at=datetime(2024, 1, 1))


def test_is_immutable() -> None:
    system_version = SystemVersion(**VALID_KWARGS)

    with pytest.raises(FrozenInstanceError):
        system_version.model = "other"  # type: ignore[misc]

"""Core domain entities: Project, SystemVersion, DatasetCase, Dataset.

Frozen dataclasses that validate their invariants on construction. See
docs/ARCHITECTURE.md section 6. Entities reference each other by string id;
a Dataset embeds its DatasetCases as an immutable tuple.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any

from evalops.domain._time import utcnow
from evalops.domain.enums import CaseOrigin, ProviderName
from evalops.domain.errors import DomainValidationError
from evalops.domain.ids import new_id


def _require_non_empty(value: str, label: str) -> None:
    if not value.strip():
        raise DomainValidationError(f"{label} must be a non-empty string")


def _require_aware(moment: datetime, label: str) -> None:
    if moment.tzinfo is None:
        raise DomainValidationError(f"{label} must be a timezone-aware datetime")


def _read_only(mapping: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return a shallow-immutable view over a private copy of ``mapping``.

    The top level cannot be mutated (no add/remove/rebind of keys). Nested
    mutable values are left as-is; this is not a deep freeze.
    """
    return MappingProxyType(dict(mapping))


@dataclass(frozen=True, slots=True)
class Project:
    """Top-level container for one system under evaluation."""

    name: str
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        _require_non_empty(self.name, "Project.name")
        _require_non_empty(self.id, "Project.id")
        _require_aware(self.created_at, "Project.created_at")


@dataclass(frozen=True, slots=True)
class SystemVersion:
    """A named, versioned, immutable configuration of a system under evaluation.

    This is the reproducibility anchor: re-running an experiment must reproduce
    exactly this configuration. ``rag_config`` and ``tool_policy`` are opaque in
    the current phase and carry no behavior.

    ``parameters``, ``rag_config`` and ``tool_policy`` are stored as read-only
    mappings: their top level cannot be mutated after construction. Nested
    mutable values (e.g. a list inside ``parameters``) are intentionally left
    mutable -- this is a shallow guarantee, not a deep freeze.
    """

    project_id: str
    name: str
    version: str
    provider: ProviderName
    model: str
    prompt_template: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    rag_config: Mapping[str, Any] | None = None
    tool_policy: Mapping[str, Any] | None = None
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not isinstance(self.provider, ProviderName):
            raise DomainValidationError(
                "SystemVersion.provider must be a ProviderName member, "
                f"got {type(self.provider).__name__}"
            )
        for value, label in (
            (self.project_id, "SystemVersion.project_id"),
            (self.name, "SystemVersion.name"),
            (self.version, "SystemVersion.version"),
            (self.model, "SystemVersion.model"),
            (self.prompt_template, "SystemVersion.prompt_template"),
            (self.id, "SystemVersion.id"),
        ):
            _require_non_empty(value, label)
        _require_aware(self.created_at, "SystemVersion.created_at")
        # Store config maps as read-only proxies over private copies, so neither
        # the caller's original dict nor the field itself can mutate the stored
        # configuration (shallow; see class docstring).
        object.__setattr__(self, "parameters", _read_only(self.parameters))
        if self.rag_config is not None:
            object.__setattr__(self, "rag_config", _read_only(self.rag_config))
        if self.tool_policy is not None:
            object.__setattr__(self, "tool_policy", _read_only(self.tool_policy))


@dataclass(frozen=True, slots=True)
class DatasetCase:
    """A single evaluation case: an input and, optionally, a reference output."""

    input: str
    expected_output: str | None = None
    origin: CaseOrigin = CaseOrigin.AUTHORED
    source_trace_id: str | None = None
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        _require_non_empty(self.input, "DatasetCase.input")
        _require_non_empty(self.id, "DatasetCase.id")
        has_trace = bool(self.source_trace_id and self.source_trace_id.strip())
        if self.origin is CaseOrigin.PROMOTED_TRACE and not has_trace:
            raise DomainValidationError(
                "DatasetCase.source_trace_id is required when origin is promoted_trace"
            )
        if self.origin is CaseOrigin.AUTHORED and self.source_trace_id is not None:
            raise DomainValidationError(
                "DatasetCase.source_trace_id must be unset when origin is authored"
            )


@dataclass(frozen=True, slots=True)
class Dataset:
    """A versioned, immutable collection of DatasetCases."""

    project_id: str
    name: str
    version: int
    cases: tuple[DatasetCase, ...]
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        _require_non_empty(self.project_id, "Dataset.project_id")
        _require_non_empty(self.name, "Dataset.name")
        _require_non_empty(self.id, "Dataset.id")
        _require_aware(self.created_at, "Dataset.created_at")
        if self.version < 1:
            raise DomainValidationError(f"Dataset.version must be >= 1, got {self.version}")
        object.__setattr__(self, "cases", tuple(self.cases))
        if not self.cases:
            raise DomainValidationError("Dataset.cases must not be empty")
        case_ids = [case.id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise DomainValidationError("Dataset.cases contains duplicate case ids")

"""Pydantic request/response schemas for the EvalOps API.

Deliberately separate from both the frozen domain dataclasses and the ORM
models. Structural validation only (types, required fields, no extras);
semantic rules stay in the domain constructors, which surface as HTTP 422.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from evalops import domain
from evalops.domain.enums import CaseOrigin, ProviderName


class _Create(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Project -------------------------------------------------------------


class ProjectCreate(_Create):
    name: str


class ProjectRead(BaseModel):
    id: str
    name: str
    created_at: datetime

    @classmethod
    def of(cls, value: domain.Project) -> ProjectRead:
        return cls(id=value.id, name=value.name, created_at=value.created_at)


# --- Dataset ------------------------------------------------------------


class DatasetCaseCreate(_Create):
    input: str
    expected_output: str | None = None
    origin: CaseOrigin = CaseOrigin.AUTHORED
    source_trace_id: str | None = None


class DatasetCreate(_Create):
    name: str
    version: int
    cases: list[DatasetCaseCreate]


class DatasetCaseRead(BaseModel):
    id: str
    input: str
    expected_output: str | None
    origin: CaseOrigin
    source_trace_id: str | None


class DatasetRead(BaseModel):
    id: str
    project_id: str
    name: str
    version: int
    created_at: datetime
    cases: list[DatasetCaseRead]

    @classmethod
    def of(cls, value: domain.Dataset) -> DatasetRead:
        return cls(
            id=value.id,
            project_id=value.project_id,
            name=value.name,
            version=value.version,
            created_at=value.created_at,
            cases=[
                DatasetCaseRead(
                    id=case.id,
                    input=case.input,
                    expected_output=case.expected_output,
                    origin=case.origin,
                    source_trace_id=case.source_trace_id,
                )
                for case in value.cases
            ],
        )


# --- SystemVersion ---------------------------------------------------


class SystemVersionCreate(_Create):
    name: str
    version: str
    provider: ProviderName
    model: str
    prompt_template: str
    parameters: dict[str, Any] = {}
    rag_config: dict[str, Any] | None = None
    tool_policy: dict[str, Any] | None = None


class SystemVersionRead(BaseModel):
    id: str
    project_id: str
    name: str
    version: str
    provider: ProviderName
    model: str
    prompt_template: str
    parameters: dict[str, Any]
    rag_config: dict[str, Any] | None
    tool_policy: dict[str, Any] | None
    created_at: datetime

    @classmethod
    def of(cls, value: domain.SystemVersion) -> SystemVersionRead:
        return cls(
            id=value.id,
            project_id=value.project_id,
            name=value.name,
            version=value.version,
            provider=value.provider,
            model=value.model,
            prompt_template=value.prompt_template,
            parameters=dict(value.parameters),
            rag_config=None if value.rag_config is None else dict(value.rag_config),
            tool_policy=None if value.tool_policy is None else dict(value.tool_policy),
            created_at=value.created_at,
        )


# --- ReleasePolicy -------------------------------------------------


class ReleasePolicyCreate(_Create):
    name: str
    thresholds: dict[str, float] = {}
    max_safety_violations: int = 0


class ReleasePolicyRead(BaseModel):
    id: str
    name: str
    thresholds: dict[str, float]
    max_safety_violations: int

    @classmethod
    def of(cls, value: domain.ReleasePolicy) -> ReleasePolicyRead:
        return cls(
            id=value.id,
            name=value.name,
            thresholds=dict(value.thresholds),
            max_safety_violations=value.max_safety_violations,
        )


# --- Experiment --------------------------------------------------


class ExperimentCreate(_Create):
    dataset_id: str
    baseline_version_id: str
    candidate_version_id: str
    repeats: int = 1
    release_policy_id: str | None = None


class ExperimentRead(BaseModel):
    id: str
    project_id: str
    dataset_id: str
    baseline_version_id: str
    candidate_version_id: str
    repeats: int
    release_policy_id: str | None
    created_at: datetime

    @classmethod
    def of(cls, value: domain.Experiment) -> ExperimentRead:
        return cls(
            id=value.id,
            project_id=value.project_id,
            dataset_id=value.dataset_id,
            baseline_version_id=value.baseline_version_id,
            candidate_version_id=value.candidate_version_id,
            repeats=value.repeats,
            release_policy_id=value.release_policy_id,
            created_at=value.created_at,
        )

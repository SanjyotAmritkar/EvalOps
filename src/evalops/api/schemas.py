"""Pydantic request/response schemas for the EvalOps API.

Deliberately separate from both the frozen domain dataclasses and the ORM
models. Structural validation only (types, required fields, no extras);
semantic rules stay in the domain constructors, which surface as HTTP 422.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from evalops import domain
from evalops.domain.enums import CaseOrigin, EvaluatorFamily, ProviderName
from evalops.execution import ExecutionSpec
from evalops.gate import GateReport
from evalops.ollama import DEFAULT_BASE_URL, DEFAULT_TIMEOUT_SECONDS


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


# --- run an experiment ---------------------------------------------


class ExecutionOptions(_Create):
    backend: Literal["mock", "ollama"] = "mock"
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    def to_spec(self) -> ExecutionSpec:
        return ExecutionSpec(
            backend=self.backend, base_url=self.base_url, timeout_seconds=self.timeout_seconds
        )


class EvaluatorSpec(_Create):
    type: str
    name: str | None = None
    case_sensitive: bool | None = None
    pattern: str | None = None


class RunRequest(_Create):
    execution: ExecutionOptions = ExecutionOptions()
    evaluators: Annotated[list[EvaluatorSpec], Field(min_length=1)]


class MetricLineRead(BaseModel):
    metric: str
    baseline_value: float
    candidate_value: float
    delta: float
    relative_delta: float | None
    direction: str
    threshold: float | None
    adverse_change: float | None
    regression: bool


class RunResponse(BaseModel):
    evaluation_result_id: str
    experiment_id: str
    dataset: str
    baseline: str
    candidate: str
    repeats: int
    counts: dict[str, int]
    decision: str
    gated: bool
    reasons: list[str]
    metrics: list[MetricLineRead]

    @classmethod
    def of(
        cls,
        *,
        experiment: domain.Experiment,
        dataset: domain.Dataset,
        baseline: domain.SystemVersion,
        candidate: domain.SystemVersion,
        runs: list[domain.EvaluationRun],
        result: domain.EvaluationResult,
        gate: GateReport,
        evaluation_result_id: str,
    ) -> RunResponse:
        verdicts = {verdict.metric: verdict for verdict in gate.verdicts}
        return cls(
            evaluation_result_id=evaluation_result_id,
            experiment_id=experiment.id,
            dataset=dataset.name,
            baseline=f"{baseline.name} {baseline.version}",
            candidate=f"{candidate.name} {candidate.version}",
            repeats=experiment.repeats,
            counts={
                "cases": len(dataset.cases),
                "runs": len(runs),
                "failures": sum(1 for run in runs if run.error is not None),
            },
            decision=gate.decision.value,
            gated=gate.gated,
            reasons=list(gate.reasons),
            metrics=[
                MetricLineRead(
                    metric=mc.metric,
                    baseline_value=mc.baseline_value,
                    candidate_value=mc.candidate_value,
                    delta=mc.delta,
                    relative_delta=mc.relative_delta,
                    direction=verdicts[mc.metric].direction,
                    threshold=verdicts[mc.metric].threshold,
                    adverse_change=verdicts[mc.metric].adverse_change,
                    regression=verdicts[mc.metric].regression,
                )
                for mc in result.metrics
            ],
        )


# --- inspecting persisted results --------------------------------


class UsageRead(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: float


class EvaluatorScoreRead(BaseModel):
    evaluator: str
    family: EvaluatorFamily
    score: float
    passed: bool | None


class EvaluationRunRead(BaseModel):
    id: str
    system_version_id: str
    case_id: str
    repeat_index: int
    output: str
    error: str | None
    usage: UsageRead
    scores: list[EvaluatorScoreRead]
    created_at: datetime

    @classmethod
    def of(
        cls, run: domain.EvaluationRun, case_result: domain.CaseResult | None
    ) -> EvaluationRunRead:
        return cls(
            id=run.id,
            system_version_id=run.system_version_id,
            case_id=run.case_id,
            repeat_index=run.repeat_index,
            output=run.output,
            error=run.error,
            usage=UsageRead(
                prompt_tokens=run.usage.prompt_tokens,
                completion_tokens=run.usage.completion_tokens,
                total_tokens=run.usage.total_tokens,
                cost_usd=run.usage.cost_usd,
                latency_ms=run.usage.latency_ms,
            ),
            scores=[]
            if case_result is None
            else [
                EvaluatorScoreRead(
                    evaluator=score.evaluator,
                    family=score.family,
                    score=score.score,
                    passed=score.passed,
                )
                for score in case_result.scores
            ],
            created_at=run.created_at,
        )


class EvaluationResultRead(BaseModel):
    """A persisted EvaluationResult with its release decision recomputed on read.

    The decision is not stored (see G-1); it is re-derived here from the
    persisted result plus the experiment's ReleasePolicy using the same
    ``evaluate_gate`` the run path uses, so a refreshed results view matches
    the original ``RunResponse``.
    """

    id: str
    experiment_id: str
    created_at: datetime
    decision: str
    gated: bool
    reasons: list[str]
    metrics: list[MetricLineRead]

    @classmethod
    def of(cls, value: domain.EvaluationResult, gate: GateReport) -> EvaluationResultRead:
        verdicts = {verdict.metric: verdict for verdict in gate.verdicts}
        return cls(
            id=value.id,
            experiment_id=value.experiment_id,
            created_at=value.created_at,
            decision=gate.decision.value,
            gated=gate.gated,
            reasons=list(gate.reasons),
            metrics=[
                MetricLineRead(
                    metric=mc.metric,
                    baseline_value=mc.baseline_value,
                    candidate_value=mc.candidate_value,
                    delta=mc.delta,
                    relative_delta=mc.relative_delta,
                    direction=verdicts[mc.metric].direction,
                    threshold=verdicts[mc.metric].threshold,
                    adverse_change=verdicts[mc.metric].adverse_change,
                    regression=verdicts[mc.metric].regression,
                )
                for mc in value.metrics
            ],
        )

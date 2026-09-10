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
from evalops.domain.enums import (
    CaseOrigin,
    EvaluatorFamily,
    JobStatus,
    ProviderName,
    TraceOrigin,
)
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


class ExpectedToolCallSpec(_Create):
    """Authored expected tool call (CP 9.2). ``arguments`` omitted / null means
    "only the tool name is expected here"."""

    name: str
    arguments: dict[str, Any] | None = None


class DatasetCaseCreate(_Create):
    input: str
    expected_output: str | None = None
    origin: CaseOrigin = CaseOrigin.AUTHORED
    source_trace_id: str | None = None
    # RAG ground truth (Phase 9): relevant document/chunk ids for this case.
    expected_retrieval_ids: list[str] = []
    # Agent ground truth (CP 9.2): the expected ordered tool trajectory.
    expected_tool_calls: list[ExpectedToolCallSpec] = []


class DatasetCreate(_Create):
    name: str
    version: int
    cases: list[DatasetCaseCreate]


class TraceDatasetCreate(_Create):
    """Promote production traces into a replayable regression Dataset (CP 8.2).

    One DatasetCase per trace id, in this order. The traces are read-only --
    promotion never mutates them."""

    name: str
    trace_ids: Annotated[list[str], Field(min_length=1)]


class ExpectedToolCallRead(BaseModel):
    name: str
    arguments: dict[str, Any] | None


class DatasetCaseRead(BaseModel):
    id: str
    input: str
    expected_output: str | None
    origin: CaseOrigin
    source_trace_id: str | None
    expected_retrieval_ids: list[str] = []
    expected_tool_calls: list[ExpectedToolCallRead] = []


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
                    expected_retrieval_ids=list(case.expected_retrieval_ids),
                    expected_tool_calls=[
                        ExpectedToolCallRead(
                            name=e.name,
                            arguments=None if e.arguments is None else dict(e.arguments),
                        )
                        for e in case.expected_tool_calls
                    ],
                )
                for case in value.cases
            ],
        )


# --- ProductionTrace (Phase 8, CP 8.1) -----------------------------


class TraceCreate(_Create):
    """Ingest one production interaction. ``metadata`` is context the caller
    chooses to send -- the API never scrapes headers, cookies, or environment,
    and callers are responsible for sending only data they may evaluate."""

    system_version_id: str
    input: str
    output: str = ""
    reference_output: str | None = None
    metadata: dict[str, Any] = {}
    latency_ms: float | None = None
    cost_usd: float | None = None
    error: str | None = None


class TraceRead(BaseModel):
    id: str
    project_id: str
    system_version_id: str
    created_at: datetime
    input: str
    output: str
    reference_output: str | None
    metadata: dict[str, Any]
    latency_ms: float | None
    cost_usd: float | None
    error: str | None
    origin: TraceOrigin

    @classmethod
    def of(cls, value: domain.ProductionTrace) -> TraceRead:
        return cls(
            id=value.id,
            project_id=value.project_id,
            system_version_id=value.system_version_id,
            created_at=value.created_at,
            input=value.input,
            output=value.output,
            reference_output=value.reference_output,
            metadata=dict(value.metadata),
            latency_ms=value.latency_ms,
            cost_usd=value.cost_usd,
            error=value.error,
            origin=value.origin,
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
    # "live" honours each SystemVersion's own provider (cross-provider runs);
    # "openai"/"anthropic" are single-provider modes. Keys are never sent here.
    backend: Literal["mock", "ollama", "openai", "anthropic", "live"] = "mock"
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
    # llm_judge only -- the judge's own provider/model, independent of the
    # system under evaluation. No API key: keys come from the environment.
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    base_url: str | None = None
    # RAG evaluators (Phase 9) -- per-evaluator pass thresholds on the graded
    # metric (0..1). retrieval_recall / context_precision / groundedness.
    min_recall: float | None = None
    min_precision: float | None = None
    min_groundedness: float | None = None
    # Agent evaluators (CP 9.2) -- pass threshold on the graded score (0..1).
    # tool_selection / tool_arguments / tool_success / tool_trajectory.
    min_score: float | None = None


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
    # CP 5.2: `regression` still drives BLOCK. `gate_outcome` distinguishes a
    # blocking regression from a threshold breach held back by weak/inconclusive
    # statistical evidence: "pass" | "regression" | "regression_inconclusive" |
    # "regression_low_evidence".
    gate_outcome: str = "pass"


class SampleSummaryRead(BaseModel):
    n: int
    mean: float
    median: float
    stdev: float


class MetricEvidenceRead(BaseModel):
    """Persisted paired-bootstrap evidence for one statistically supported
    metric (CP 5.2). Present for success_rate, evaluator pass-rates, and
    latency_ms.mean; absent for latency_ms.p95 / cost_usd.total."""

    metric: str
    kind: str
    n_pairs: int
    baseline: SampleSummaryRead
    candidate: SampleSummaryRead
    paired_delta: SampleSummaryRead
    delta: float
    relative_change: float | None
    confidence_level: float
    ci_low: float | None
    ci_high: float | None
    ci_excludes_zero: bool
    insufficient_evidence: bool
    dropped_provider_failures: int
    method: str

    @classmethod
    def of(cls, value: domain.MetricEvidence) -> MetricEvidenceRead:
        def _summary(s: domain.SampleSummary) -> SampleSummaryRead:
            return SampleSummaryRead(n=s.n, mean=s.mean, median=s.median, stdev=s.stdev)

        return cls(
            metric=value.metric,
            kind=value.kind,
            n_pairs=value.n_pairs,
            baseline=_summary(value.baseline),
            candidate=_summary(value.candidate),
            paired_delta=_summary(value.paired_delta),
            delta=value.delta,
            relative_change=value.relative_change,
            confidence_level=value.confidence_level,
            ci_low=value.ci_low,
            ci_high=value.ci_high,
            ci_excludes_zero=value.ci_excludes_zero,
            insufficient_evidence=value.insufficient_evidence,
            dropped_provider_failures=value.dropped_provider_failures,
            method=value.method,
        )


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
    # CP 5.2 -- additive, backward compatible.
    advisories: list[str] = []
    evidence: list[MetricEvidenceRead] = []

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
                    gate_outcome=verdicts[mc.metric].outcome,
                )
                for mc in result.metrics
            ],
            advisories=list(gate.advisories),
            evidence=[MetricEvidenceRead.of(e) for e in result.evidence],
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


class RetrievedItemRead(BaseModel):
    """One retrieved document/chunk an external RAG system reported (Phase 9)."""

    doc_id: str
    content: str
    rank: int
    score: float | None


class ToolCallRead(BaseModel):
    """One tool invocation an external agent reported (Phase 9, CP 9.2)."""

    name: str
    arguments: dict[str, Any]
    result: Any = None
    ok: bool
    error: str | None


class EvaluationRunRead(BaseModel):
    id: str
    system_version_id: str
    case_id: str
    repeat_index: int
    output: str
    error: str | None
    usage: UsageRead
    scores: list[EvaluatorScoreRead]
    #: RAG retrieval evidence, empty for text-only runs (Phase 9).
    retrieval: list[RetrievedItemRead] = []
    #: Agent tool-call evidence, empty for non-agent runs (CP 9.2).
    tool_calls: list[ToolCallRead] = []
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
            retrieval=[
                RetrievedItemRead(
                    doc_id=item.doc_id,
                    content=item.content,
                    rank=item.rank,
                    score=item.score,
                )
                for item in run.retrieval
            ],
            tool_calls=[
                ToolCallRead(
                    name=tc.name,
                    arguments=dict(tc.arguments),
                    result=tc.result,
                    ok=tc.ok,
                    error=tc.error,
                )
                for tc in run.tool_calls
            ],
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
    # CP 5.2 -- additive, backward compatible. Persisted evidence + recomputed
    # advisories survive a page refresh identically to the sync RunResponse.
    advisories: list[str] = []
    evidence: list[MetricEvidenceRead] = []

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
                    gate_outcome=verdicts[mc.metric].outcome,
                )
                for mc in value.metrics
            ],
            advisories=list(gate.advisories),
            evidence=[MetricEvidenceRead.of(e) for e in value.evidence],
        )


# --- async job -----------------------------------------------------


class AsyncJobRead(BaseModel):
    """The durable status of a background experiment run. PostgreSQL is
    authoritative -- these fields come from the ``async_job`` row, never from
    Celery/Redis."""

    id: str
    experiment_id: str
    status: JobStatus
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    evaluation_result_id: str | None
    error: str | None
    celery_task_id: str | None

    @classmethod
    def of(cls, value: domain.AsyncJob) -> AsyncJobRead:
        return cls(
            id=value.id,
            experiment_id=value.experiment_id,
            status=value.status,
            created_at=value.created_at,
            started_at=value.started_at,
            completed_at=value.completed_at,
            evaluation_result_id=value.evaluation_result_id,
            error=value.error,
            celery_task_id=value.celery_task_id,
        )


# --- LLM-judge calibration (Phase 6, CP 6.2) ------------------------


class LabeledJudgeExampleIn(_Create):
    input: str
    output: str
    human_pass: bool
    reference: str | None = None


class JudgeCalibrationCreate(_Create):
    """Configure and run a calibration. No API key -- credentials are read from
    the environment only."""

    provider: str
    model: str
    name: str | None = None
    temperature: float | None = None
    base_url: str | None = None
    examples: Annotated[list[LabeledJudgeExampleIn], Field(min_length=1)]


class JudgeCalibrationMetricsRead(BaseModel):
    total: int
    scored: int
    failures: int
    agreements: int
    agreement_rate: float | None
    true_positives: int
    true_negatives: int
    false_positives: int
    false_negatives: int
    precision: float | None
    recall: float | None
    f1: float | None


class JudgeCalibrationCaseRead(BaseModel):
    input: str
    output: str
    reference: str | None
    human_pass: bool
    judge_pass: bool | None
    judge_score: float | None
    judge_reasoning: str | None
    error: str | None


class JudgeCalibrationRead(BaseModel):
    id: str
    created_at: datetime
    judge_provider: ProviderName
    judge_model: str
    judge_name: str
    judge_temperature: float
    rubric_id: str
    metrics: JudgeCalibrationMetricsRead
    cases: list[JudgeCalibrationCaseRead]

    @classmethod
    def of(cls, value: domain.JudgeCalibration) -> JudgeCalibrationRead:
        m = value.metrics
        return cls(
            id=value.id,
            created_at=value.created_at,
            judge_provider=value.judge_provider,
            judge_model=value.judge_model,
            judge_name=value.judge_name,
            judge_temperature=value.judge_temperature,
            rubric_id=value.rubric_id,
            metrics=JudgeCalibrationMetricsRead(
                total=m.total,
                scored=m.scored,
                failures=m.failures,
                agreements=m.agreements,
                agreement_rate=m.agreement_rate,
                true_positives=m.true_positives,
                true_negatives=m.true_negatives,
                false_positives=m.false_positives,
                false_negatives=m.false_negatives,
                precision=m.precision,
                recall=m.recall,
                f1=m.f1,
            ),
            cases=[
                JudgeCalibrationCaseRead(
                    input=case.input,
                    output=case.output,
                    reference=case.reference,
                    human_pass=case.human_pass,
                    judge_pass=case.judge_pass,
                    judge_score=case.judge_score,
                    judge_reasoning=case.judge_reasoning,
                    error=case.error,
                )
                for case in value.cases
            ],
        )

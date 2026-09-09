"""Statistical regression primitives for repeated baseline/candidate evaluations.

Additive to Phase 1 aggregation (:mod:`evalops.aggregate`): nothing here changes
an ``EvaluationResult`` or a PASS/BLOCK decision. Given the raw per-run records
of a :class:`~evalops.runner.RunOutcome`, this module

1. builds **paired observations** for baseline vs candidate, matched by
   ``(case_id, repeat_index)`` and ordered deterministically;
2. computes descriptive **summaries** (n, mean, median, sample stdev) for the
   two series and for their paired differences;
3. computes a **deterministic paired-bootstrap percentile confidence interval**
   for the baseline->candidate delta; and
4. packages all of that per metric into a :class:`MetricEvidence` object that a
   later release-gating phase (or an API surface) can consume.

Pure standard library -- no NumPy/SciPy. See ``docs/ARCHITECTURE.md`` section 8
for the rationale (nondeterministic LLM output, small N, no distributional
assumption, pairing removes per-case difficulty variance).
"""

from __future__ import annotations

import random
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil, floor

from evalops.domain.entities import CaseResult, EvaluationRun, Experiment
from evalops.domain.value_objects import MetricEvidence, MetricKind, SampleSummary
from evalops.errors import ConfigError
from evalops.runner import RunOutcome

# Re-exported for callers that import these from evalops.stats (they are defined
# in the domain so an EvaluationResult can carry them; the maths stays here).
__all__ = [
    "MetricEvidence",
    "MetricKind",
    "PairedSeries",
    "SampleSummary",
    "build_statistical_evidence",
    "metric_evidence",
    "paired_bootstrap_ci",
    "paired_observations",
    "summarize",
]

#: Default two-sided confidence level for the bootstrap interval.
DEFAULT_CONFIDENCE_LEVEL = 0.95
#: Bootstrap resample count. Deterministic given the seed; tunable per call.
DEFAULT_RESAMPLES = 2000
#: Fixed RNG seed so intervals are reproducible across runs and machines.
DEFAULT_SEED = 0x5EED0501
#: Fewer comparable pairs than this: no interval is reported and
#: ``insufficient_evidence`` is set. The point estimates are still produced.
MIN_PAIRS_FOR_CI = 3
#: ``method`` tag recorded on every :class:`MetricEvidence`.
BOOTSTRAP_METHOD = "paired_bootstrap_percentile"


# --- descriptive summaries -------------------------------------------------


def summarize(values: Sequence[float]) -> SampleSummary:
    """Summarise ``values``. An empty series is all-zeros (n == 0)."""
    n = len(values)
    if n == 0:
        return SampleSummary(n=0, mean=0.0, median=0.0, stdev=0.0)
    return SampleSummary(
        n=n,
        mean=statistics.fmean(values),
        median=statistics.median(values),
        stdev=statistics.stdev(values) if n >= 2 else 0.0,
    )


# --- paired observations -------------------------------------------------


@dataclass(frozen=True, slots=True)
class PairedSeries:
    """Baseline and candidate per-run observations for one metric, aligned.

    ``baseline[i]`` and ``candidate[i]`` come from the same
    ``(case_id, repeat_index)`` and are ordered by that key.
    """

    metric: str
    kind: MetricKind
    baseline: tuple[float, ...]
    candidate: tuple[float, ...]
    matched_pairs: int  # (case_id, repeat_index) keys present for BOTH versions
    comparable_pairs: int  # matched pairs usable for THIS metric (== len(baseline))
    dropped_provider_failures: int  # matched pairs excluded here for a provider error
    unmatched_runs: int  # runs whose (case_id, repeat_index) had no counterpart


def _pair_key(run: EvaluationRun) -> tuple[str, int]:
    return (run.case_id, run.repeat_index)


def _runs_by_key(
    runs: Sequence[EvaluationRun], version_id: str
) -> dict[tuple[str, int], EvaluationRun]:
    by_key: dict[tuple[str, int], EvaluationRun] = {}
    for run in runs:
        if run.system_version_id != version_id:
            continue
        key = _pair_key(run)
        if key in by_key:
            raise ConfigError(
                f"version {version_id!r} has more than one run for case {key[0]!r} repeat {key[1]}"
            )
        by_key[key] = run
    return by_key


def _success_obs(run: EvaluationRun) -> float:
    """1.0 for a run with no provider error, else 0.0."""
    return 1.0 if run.error is None else 0.0


def _pass_obs(
    run: EvaluationRun,
    case_results: dict[str, CaseResult],
    evaluator_name: str,
) -> float:
    """1.0 when the run succeeded *and* ``evaluator_name`` passed, else 0.0.

    A failed provider run contributes 0.0 -- the same denominator rule Phase 1
    aggregation uses for pass-rate.
    """
    if run.error is not None:
        return 0.0
    case_result = case_results.get(run.id)
    if case_result is None:
        raise ConfigError(f"successful run {run.id!r} has no case result")
    score = next((s for s in case_result.scores if s.evaluator == evaluator_name), None)
    if score is None:
        raise ConfigError(
            f"successful run {run.id!r} is missing the {evaluator_name!r} evaluator score"
        )
    return 1.0 if score.passed else 0.0


def _series(
    metric: str,
    kind: MetricKind,
    baseline: tuple[float, ...],
    candidate: tuple[float, ...],
    *,
    matched: int,
    comparable: int,
    dropped: int,
    unmatched: int,
) -> PairedSeries:
    return PairedSeries(
        metric=metric,
        kind=kind,
        baseline=baseline,
        candidate=candidate,
        matched_pairs=matched,
        comparable_pairs=comparable,
        dropped_provider_failures=dropped,
        unmatched_runs=unmatched,
    )


def paired_observations(
    experiment: Experiment,
    outcome: RunOutcome,
    *,
    evaluator_names: Sequence[str],
) -> dict[str, PairedSeries]:
    """Pair baseline/candidate runs and project each gateable metric onto
    per-pair scalar observations.

    Pairs are matched by ``(case_id, repeat_index)`` and only keys present for
    **both** versions are used, ordered by that key (deterministic). Provider
    failures are handled per metric:

    * ``success_rate`` -- binary indicator per run (0.0 on error); every
      comparable pair contributes.
    * ``<name>.pass_rate`` -- binary indicator per run (0.0 on error or a
      non-passing score); every comparable pair contributes.
    * ``latency_ms.mean`` -- the run's latency; a pair is **dropped** when
      either side errored (a failed run has no meaningful latency).
    * ``cost_usd.mean`` -- the run's recorded cost; a failed run genuinely
      costs ~0, so every comparable pair contributes.

    Returns an insertion-ordered dict in Phase 1 aggregation order.
    """
    names = list(evaluator_names)
    if len(names) != len(set(names)):
        raise ConfigError(f"evaluator_names contains duplicates: {sorted(names)}")

    baseline_by_key = _runs_by_key(outcome.runs, experiment.baseline_version_id)
    candidate_by_key = _runs_by_key(outcome.runs, experiment.candidate_version_id)

    common = sorted(baseline_by_key.keys() & candidate_by_key.keys())
    matched = len(common)
    unmatched = (len(baseline_by_key) - matched) + (len(candidate_by_key) - matched)

    case_results: dict[str, CaseResult] = {cr.run_id: cr for cr in outcome.case_results}
    pairs = [(baseline_by_key[k], candidate_by_key[k]) for k in common]

    series: dict[str, PairedSeries] = {}

    series["success_rate"] = _series(
        "success_rate",
        "binary",
        tuple(_success_obs(b) for b, _ in pairs),
        tuple(_success_obs(c) for _, c in pairs),
        matched=matched,
        comparable=matched,
        dropped=0,
        unmatched=unmatched,
    )

    for name in names:
        metric = f"{name}.pass_rate"
        series[metric] = _series(
            metric,
            "binary",
            tuple(_pass_obs(b, case_results, name) for b, _ in pairs),
            tuple(_pass_obs(c, case_results, name) for _, c in pairs),
            matched=matched,
            comparable=matched,
            dropped=0,
            unmatched=unmatched,
        )

    both_ok = [(b, c) for b, c in pairs if b.error is None and c.error is None]
    series["latency_ms.mean"] = _series(
        "latency_ms.mean",
        "continuous",
        tuple(b.usage.latency_ms for b, _ in both_ok),
        tuple(c.usage.latency_ms for _, c in both_ok),
        matched=matched,
        comparable=len(both_ok),
        dropped=matched - len(both_ok),
        unmatched=unmatched,
    )

    series["cost_usd.mean"] = _series(
        "cost_usd.mean",
        "continuous",
        tuple(b.usage.cost_usd for b, _ in pairs),
        tuple(c.usage.cost_usd for _, c in pairs),
        matched=matched,
        comparable=matched,
        dropped=0,
        unmatched=unmatched,
    )

    return series


# --- paired bootstrap ---------------------------------------------------


def _percentile(ordered: Sequence[float], q: float) -> float:
    """Linear-interpolation percentile of an already-sorted sequence, ``q`` in [0, 1]."""
    if len(ordered) == 1:
        return ordered[0]
    pos = q * (len(ordered) - 1)
    lo, hi = floor(pos), ceil(pos)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def paired_bootstrap_ci(
    baseline: Sequence[float],
    candidate: Sequence[float],
    *,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
) -> tuple[float | None, float | None]:
    """Deterministic percentile CI for ``mean(candidate_i - baseline_i)``.

    Resamples the paired differences with replacement ``resamples`` times from a
    ``random.Random(seed)`` stream. Returns ``(None, None)`` when there are
    fewer than :data:`MIN_PAIRS_FOR_CI` pairs; a zero-variance difference sample
    (all differences equal, including all-zero) collapses to a point interval.
    """
    if not 0.0 < confidence_level < 1.0:
        raise ConfigError(f"confidence_level must be in (0, 1), got {confidence_level!r}")
    n = len(baseline)
    if len(candidate) != n:
        raise ConfigError("baseline and candidate must have the same length")
    if n < MIN_PAIRS_FOR_CI:
        return None, None

    diffs = [cv - bv for bv, cv in zip(baseline, candidate, strict=True)]
    if all(d == diffs[0] for d in diffs):
        return diffs[0], diffs[0]

    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(resamples):
        total = 0.0
        for _ in range(n):
            total += diffs[rng.randrange(n)]
        estimates.append(total / n)
    estimates.sort()

    tail = (1.0 - confidence_level) / 2.0
    return _percentile(estimates, tail), _percentile(estimates, 1.0 - tail)


# --- evidence -----------------------------------------------------------


def metric_evidence(
    metric: str,
    kind: MetricKind,
    baseline: Sequence[float],
    candidate: Sequence[float],
    *,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
    dropped_provider_failures: int = 0,
) -> MetricEvidence:
    """Build :class:`MetricEvidence` from two aligned observation series."""
    if len(baseline) != len(candidate):
        raise ConfigError("baseline and candidate must have the same length")

    b_summary = summarize(baseline)
    c_summary = summarize(candidate)
    diffs = [cv - bv for bv, cv in zip(baseline, candidate, strict=True)]
    delta_summary = summarize(diffs)
    n = len(diffs)

    delta = c_summary.mean - b_summary.mean
    relative_change = None if b_summary.mean == 0.0 else delta / b_summary.mean
    ci_low, ci_high = paired_bootstrap_ci(
        baseline,
        candidate,
        confidence_level=confidence_level,
        resamples=resamples,
        seed=seed,
    )
    insufficient = n < MIN_PAIRS_FOR_CI
    excludes_zero = (
        not insufficient
        and ci_low is not None
        and ci_high is not None
        and (ci_low > 0.0 or ci_high < 0.0)
    )
    return MetricEvidence(
        metric=metric,
        kind=kind,
        n_pairs=n,
        baseline=b_summary,
        candidate=c_summary,
        paired_delta=delta_summary,
        delta=delta,
        relative_change=relative_change,
        confidence_level=confidence_level,
        ci_low=ci_low,
        ci_high=ci_high,
        ci_excludes_zero=excludes_zero,
        insufficient_evidence=insufficient,
        method=BOOTSTRAP_METHOD,
        resamples=resamples,
        seed=seed,
        dropped_provider_failures=dropped_provider_failures,
    )


def build_statistical_evidence(
    experiment: Experiment,
    outcome: RunOutcome,
    *,
    evaluator_names: Sequence[str],
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
) -> tuple[MetricEvidence, ...]:
    """One :class:`MetricEvidence` per gateable metric, in aggregation order.

    Reads the same ``RunOutcome`` Phase 1 aggregation reads and changes nothing
    about the ``EvaluationResult`` or the gate. Each metric gets its own
    ``seed + i`` so the per-metric bootstraps are independent yet reproducible.
    """
    series = paired_observations(experiment, outcome, evaluator_names=evaluator_names)
    return tuple(
        metric_evidence(
            s.metric,
            s.kind,
            s.baseline,
            s.candidate,
            confidence_level=confidence_level,
            resamples=resamples,
            seed=seed + i,
            dropped_provider_failures=s.dropped_provider_failures,
        )
        for i, s in enumerate(series.values())
    )

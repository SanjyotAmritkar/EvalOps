"""Deterministic agent / tool evaluators (Phase 9, CP 9.2).

Score the tool-call trajectory an external agent reported on an
``EvaluationRun`` against the authored ``DatasetCase.expected_tool_calls``.
EvalOps observes and evaluates tool behaviour; it never executes a tool, plans,
or judges semantic task correctness.

Each is an ordinary ``Evaluator``: it emits an ``EvaluatorScore`` with a graded
value in ``score`` (0..1) and a threshold-derived ``passed``, so
``<name>.pass_rate`` and ``<name>.mean_score`` both flow through the existing
aggregation / paired-bootstrap evidence / release-gate path with no
agent-specific handling downstream.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from evalops.domain.entities import DatasetCase, EvaluationRun
from evalops.domain.enums import EvaluatorFamily
from evalops.domain.value_objects import EvaluatorScore
from evalops.errors import ConfigError

_FAMILY = EvaluatorFamily.DETERMINISTIC

#: Trajectory / tool-argument metrics are *exact structural* checks. They do not
#: prove the agent solved the task, and they penalise valid alternative
#: trajectories (a different but correct tool order scores below 1.0).
AGENT_METRIC_NOTE = (
    "tool_selection / tool_arguments / tool_success / tool_trajectory are "
    "DETERMINISTIC STRUCTURAL metrics over reported tool activity. They measure "
    "adherence to an authored expectation, not semantic task correctness, and "
    "tool_trajectory is sensitive to valid alternative orderings."
)


def _canonical(value: Any) -> Any:
    """Order-independent canonical form for deterministic structural comparison.

    Mapping -> sorted tuple of (str key, canonical value); sequence -> tuple of
    canonical values; scalars unchanged. This is *structural* equality only --
    it makes no claim of semantic equivalence.
    """
    if isinstance(value, Mapping):
        return tuple(sorted((str(k), _canonical(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_canonical(v) for v in value)
    return value


def _expected_calls(reference: DatasetCase, evaluator_name: str) -> Sequence[Any]:
    if not reference.expected_tool_calls:
        raise ConfigError(
            f"evaluator {evaluator_name!r} requires expected_tool_calls, "
            f"but case {reference.id!r} has none"
        )
    return reference.expected_tool_calls


def _threshold(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0:
        raise ConfigError(f"{label} must be a number within [0, 1]")
    return float(value)


def _lcs_len(a: Sequence[str], b: Sequence[str]) -> int:
    """Length of the longest common subsequence of two name sequences."""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for x in a:
        curr = [0]
        for j, y in enumerate(b, start=1):
            curr.append(prev[j - 1] + 1 if x == y else max(prev[j], curr[j - 1]))
        prev = curr
    return prev[-1]


@dataclass(frozen=True, slots=True)
class ToolSelection:
    """Jaccard overlap of expected vs observed tool *names* (order-independent).

    ``score = |expected ∩ observed| / |expected union observed|`` over name sets.

    * missing an expected tool -> smaller intersection -> lower score
    * an unexpected extra tool -> larger union -> lower score
    * duplicate names (expected or observed) collapse -- no effect
    * ordering is ignored
    * no ``expected_tool_calls`` -> :class:`ConfigError` (never fabricated)
    * no observed calls -> ``0.0``

    ``passed`` is ``score >= min_score`` (default ``1.0``).
    """

    min_score: float = 1.0
    name: str = "tool_selection"

    family = _FAMILY

    def __post_init__(self) -> None:
        _threshold(self.min_score, f"evaluator {self.name!r} min_score")

    def evaluate(self, run: EvaluationRun, reference: DatasetCase) -> EvaluatorScore:
        expected = {e.name for e in _expected_calls(reference, self.name)}
        observed = {tc.name for tc in run.tool_calls}
        union = expected | observed
        score = len(expected & observed) / len(union) if union else 1.0
        return EvaluatorScore(
            evaluator=self.name, family=self.family, score=score, passed=score >= self.min_score
        )


@dataclass(frozen=True, slots=True)
class ToolArguments:
    """Fraction of arg-labelled expectations whose observed call's arguments are
    a **structural** match (key-order independent, nested-aware).

    Only ``ExpectedToolCall`` entries that carry ``arguments`` are checked. The
    k-th such expectation for tool ``T`` is compared against the k-th observed
    call to ``T`` (positional pairing for repeated tool names). A missing
    counterpart counts as unmatched.

    * exact structural equality via a canonical form -- missing/extra keys or a
      changed nested value -> not a match
    * JSON object key order does not matter
    * a case with no arg-labelled expectations -> :class:`ConfigError`

    Structural equality is **not** semantic equivalence. ``passed`` is
    ``score >= min_score`` (default ``1.0``).
    """

    min_score: float = 1.0
    name: str = "tool_arguments"

    family = _FAMILY

    def __post_init__(self) -> None:
        _threshold(self.min_score, f"evaluator {self.name!r} min_score")

    def evaluate(self, run: EvaluationRun, reference: DatasetCase) -> EvaluatorScore:
        labelled = [e for e in _expected_calls(reference, self.name) if e.arguments is not None]
        if not labelled:
            raise ConfigError(
                f"evaluator {self.name!r} requires at least one expected_tool_calls entry "
                f"with explicit arguments, but case {reference.id!r} has none"
            )
        observed_by_name: dict[str, list[Any]] = {}
        for tc in run.tool_calls:
            observed_by_name.setdefault(tc.name, []).append(tc)

        seen: dict[str, int] = {}
        matched = 0
        for expected in labelled:
            index = seen.get(expected.name, 0)
            seen[expected.name] = index + 1
            candidates = observed_by_name.get(expected.name, [])
            if index < len(candidates) and _canonical(candidates[index].arguments) == _canonical(
                expected.arguments
            ):
                matched += 1
        score = matched / len(labelled)
        return EvaluatorScore(
            evaluator=self.name, family=self.family, score=score, passed=score >= self.min_score
        )


@dataclass(frozen=True, slots=True)
class ToolSuccess:
    """Observed tool-execution success rate: ``successful calls / observed calls``.

    Needs no authored labels. **Zero observed calls -> ``1.0``** (no tool
    failure was observed; whether the agent *should* have called a tool is
    ``tool_selection``'s concern). ``passed`` is ``score >= min_score``
    (default ``1.0``).
    """

    min_score: float = 1.0
    name: str = "tool_success"

    family = _FAMILY

    def __post_init__(self) -> None:
        _threshold(self.min_score, f"evaluator {self.name!r} min_score")

    def evaluate(self, run: EvaluationRun, reference: DatasetCase) -> EvaluatorScore:
        calls = run.tool_calls
        score = sum(1 for c in calls if c.ok) / len(calls) if calls else 1.0
        return EvaluatorScore(
            evaluator=self.name, family=self.family, score=score, passed=score >= self.min_score
        )


@dataclass(frozen=True, slots=True)
class ToolTrajectory:
    """Ordered adherence of the observed tool-name sequence to the expected one.

    ``score = 2 * LCS(expected, observed) / (len(expected) + len(observed))``
    (a sequence Dice coefficient) -- ``1.0`` only for the exact expected order.

    This is **exact trajectory adherence, not agent/task correctness**. It is
    sensitive to valid alternative trajectories: an agent that reaches the same
    result via a different but legitimate tool order scores below ``1.0``.

    * no ``expected_tool_calls`` -> :class:`ConfigError`
    * no observed calls -> ``0.0``

    ``passed`` is ``score >= min_score`` (default ``1.0``).
    """

    min_score: float = 1.0
    name: str = "tool_trajectory"

    family = _FAMILY

    def __post_init__(self) -> None:
        _threshold(self.min_score, f"evaluator {self.name!r} min_score")

    def evaluate(self, run: EvaluationRun, reference: DatasetCase) -> EvaluatorScore:
        expected_seq = [e.name for e in _expected_calls(reference, self.name)]
        observed_seq = [tc.name for tc in run.tool_calls]
        denom = len(expected_seq) + len(observed_seq)
        score = (2 * _lcs_len(expected_seq, observed_seq) / denom) if denom else 1.0
        return EvaluatorScore(
            evaluator=self.name, family=self.family, score=score, passed=score >= self.min_score
        )


#: Config ``type`` -> which authored labels every case needs:
#: "names" = ``expected_tool_calls`` present; "args" = at least one entry with
#: explicit ``arguments``; "none" = no labels required.
AGENT_EVALUATOR_LABELS: dict[str, str] = {
    "tool_selection": "names",
    "tool_arguments": "args",
    "tool_success": "none",
    "tool_trajectory": "names",
}

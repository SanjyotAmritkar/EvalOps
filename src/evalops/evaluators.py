"""Deterministic evaluators.

Each implements the domain ``Evaluator`` protocol: it scores one
``EvaluationRun`` against its reference ``DatasetCase`` and returns an
``EvaluatorScore`` in the ``DETERMINISTIC`` family with score 1.0 (pass) or
0.0 (fail). No fuzzy matching, semantic similarity, weighting, composites, or
pipelines.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from evalops.domain.entities import DatasetCase, EvaluationRun
from evalops.domain.enums import EvaluatorFamily
from evalops.domain.value_objects import EvaluatorScore
from evalops.errors import ConfigError


def _score(name: str, *, passed: bool) -> EvaluatorScore:
    return EvaluatorScore(
        evaluator=name,
        family=EvaluatorFamily.DETERMINISTIC,
        score=1.0 if passed else 0.0,
        passed=passed,
    )


def _reference_output(reference: DatasetCase, evaluator_name: str) -> str:
    if reference.expected_output is None:
        raise ConfigError(
            f"evaluator {evaluator_name!r} requires expected_output, "
            f"but case {reference.id!r} has none"
        )
    return reference.expected_output


@dataclass(frozen=True, slots=True)
class ExactMatch:
    """Pass when the run output equals the reference, ignoring surrounding
    whitespace. Case-sensitive by default.
    """

    case_sensitive: bool = True
    name: str = "exact_match"

    family = EvaluatorFamily.DETERMINISTIC

    def evaluate(self, run: EvaluationRun, reference: DatasetCase) -> EvaluatorScore:
        actual = run.output.strip()
        target = _reference_output(reference, self.name).strip()
        if not self.case_sensitive:
            actual, target = actual.casefold(), target.casefold()
        return _score(self.name, passed=actual == target)


@dataclass(frozen=True, slots=True)
class Contains:
    """Pass when the reference occurs as a substring of the run output.
    Case-insensitive by default. Whitespace is not normalised.
    """

    case_sensitive: bool = False
    name: str = "contains"

    family = EvaluatorFamily.DETERMINISTIC

    def evaluate(self, run: EvaluationRun, reference: DatasetCase) -> EvaluatorScore:
        needle = _reference_output(reference, self.name)
        haystack = run.output
        if not self.case_sensitive:
            needle, haystack = needle.casefold(), haystack.casefold()
        return _score(self.name, passed=needle in haystack)


@dataclass(frozen=True, slots=True)
class RegexMatch:
    """Pass when the configured pattern is found anywhere in the run output
    (``re.search`` semantics). Does not use the reference. An invalid pattern
    is rejected at construction, never during evaluation.
    """

    pattern: str
    name: str = "regex_match"

    family = EvaluatorFamily.DETERMINISTIC

    def __post_init__(self) -> None:
        try:
            re.compile(self.pattern)
        except re.error as exc:
            raise ConfigError(f"invalid regex pattern for evaluator {self.name!r}: {exc}") from exc

    def evaluate(self, run: EvaluationRun, reference: DatasetCase) -> EvaluatorScore:
        return _score(self.name, passed=re.search(self.pattern, run.output) is not None)

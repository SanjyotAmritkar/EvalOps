"""Contract tests for the ProviderClient and Evaluator protocols.

These use throwaway in-test fakes (not shipped implementations) to pin the
shape of each contract: static structural conformance, runtime isinstance
behaviour, return types, and the ProviderError hierarchy.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass

import pytest

from evalops.domain.contracts import Evaluator, ProviderClient, ProviderError, ProviderResponse
from evalops.domain.entities import DatasetCase, EvaluationRun, SystemVersion
from evalops.domain.enums import EvaluatorFamily, ProviderName
from evalops.domain.errors import EvalOpsError
from evalops.domain.value_objects import EvaluatorScore, UsageMetrics


def _system_version() -> SystemVersion:
    return SystemVersion(
        project_id="p",
        name="cfg",
        version="v1",
        provider=ProviderName.OPENAI,
        model="m",
        prompt_template="Q: {q}",
    )


def _run(output: str) -> EvaluationRun:
    return EvaluationRun(
        experiment_id="e",
        system_version_id="sv",
        case_id="c",
        repeat_index=0,
        output=output,
    )


class _FakeProvider:
    name = "fake"

    def complete(self, prompt: str, config: SystemVersion) -> ProviderResponse:
        return ProviderResponse(text=f"echo:{prompt}", usage=UsageMetrics(latency_ms=1.0))


class _FailingProvider:
    name = "failing"

    def complete(self, prompt: str, config: SystemVersion) -> ProviderResponse:
        raise ProviderError("upstream 503")


class _ProviderMissingComplete:
    name = "broken"


class _FakeEvaluator:
    name = "exact_match"
    family = EvaluatorFamily.DETERMINISTIC

    def evaluate(self, run: EvaluationRun, reference: DatasetCase) -> EvaluatorScore:
        passed = run.output == reference.expected_output
        return EvaluatorScore(
            evaluator=self.name,
            family=self.family,
            score=1.0 if passed else 0.0,
            passed=passed,
        )


class _EvaluatorMissingEvaluate:
    name = "broken"
    family = EvaluatorFamily.DETERMINISTIC


@dataclass(frozen=True)
class _FrozenProvider:
    """A frozen implementation: name is a read-only field, not a settable attr."""

    name: str = "frozen-provider"

    def complete(self, prompt: str, config: SystemVersion) -> ProviderResponse:
        return ProviderResponse(text=prompt, usage=UsageMetrics())


@dataclass(frozen=True)
class _FrozenEvaluator:
    """A frozen implementation: name and family are read-only fields."""

    name: str = "frozen-evaluator"
    family: EvaluatorFamily = EvaluatorFamily.DETERMINISTIC

    def evaluate(self, run: EvaluationRun, reference: DatasetCase) -> EvaluatorScore:
        return EvaluatorScore(evaluator=self.name, family=self.family, score=1.0)


def test_provider_client_conformance() -> None:
    client: ProviderClient = _FakeProvider()  # static structural check

    assert isinstance(client, ProviderClient)
    assert not isinstance(_ProviderMissingComplete(), ProviderClient)


def test_read_only_implementations_satisfy_the_protocols() -> None:
    # Frozen dataclasses expose name/family as read-only fields; the read-only
    # protocol properties must accept them (static assignment + runtime check).
    provider: ProviderClient = _FrozenProvider()
    evaluator: Evaluator = _FrozenEvaluator()

    assert isinstance(provider, ProviderClient)
    assert isinstance(evaluator, Evaluator)
    with pytest.raises(FrozenInstanceError):
        provider.name = "changed"  # type: ignore[misc]


def test_provider_complete_returns_a_provider_response() -> None:
    response = _FakeProvider().complete("2 + 2 = ?", _system_version())

    assert isinstance(response, ProviderResponse)
    assert response.text == "echo:2 + 2 = ?"
    assert response.usage.latency_ms == 1.0


def test_provider_error_is_an_evalops_error() -> None:
    assert issubclass(ProviderError, EvalOpsError)

    with pytest.raises(EvalOpsError):
        _FailingProvider().complete("x", _system_version())


def test_provider_response_is_immutable() -> None:
    response = ProviderResponse(text="hi", usage=UsageMetrics())

    with pytest.raises(FrozenInstanceError):
        response.text = "bye"  # type: ignore[misc]


def test_evaluator_conformance() -> None:
    evaluator: Evaluator = _FakeEvaluator()  # static structural check

    assert isinstance(evaluator, Evaluator)
    assert not isinstance(_EvaluatorMissingEvaluate(), Evaluator)


def test_evaluator_evaluate_returns_an_evaluator_score() -> None:
    reference = DatasetCase(input="2 + 2 = ?", expected_output="4")

    hit = _FakeEvaluator().evaluate(_run("4"), reference)
    miss = _FakeEvaluator().evaluate(_run("5"), reference)

    assert isinstance(hit, EvaluatorScore)
    assert (hit.passed, hit.score) == (True, 1.0)
    assert (miss.passed, miss.score) == (False, 0.0)

"""LLM-judge evaluator foundation (CP 6.1).

A small, deliberately minimal ``Evaluator`` that asks a configured
``ProviderClient`` to score a candidate output against the case input and an
optional reference answer, using a fixed rubric this module owns.

Scope for CP 6.1:

* one rubric, one structured verdict (``pass``/``fail`` + optional ``score``);
* the judge's provider/model are configured **independently** of the system
  under evaluation;
* low temperature by default;
* malformed judge output raises :class:`~evalops.errors.JudgeError` -- it never
  degrades to a silent pass. Because the runner lets an evaluator exception
  propagate, this aborts the run loudly.

Calibration / judge-vs-human agreement metrics are **not** here; that is CP 6.2.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, ClassVar

from evalops.domain.contracts import ProviderClient
from evalops.domain.entities import DatasetCase, EvaluationRun, SystemVersion
from evalops.domain.enums import EvaluatorFamily, ProviderName
from evalops.domain.value_objects import EvaluatorScore
from evalops.errors import JudgeError

#: Fixed, version-controlled rubric. Deterministic: no timestamps, ids, or
#: randomness. The judge must answer with exactly one JSON object.
JUDGE_RUBRIC = (
    "You are a strict, impartial evaluation judge. Decide whether the CANDIDATE "
    "ANSWER is a correct and appropriate response to the INPUT. If a REFERENCE "
    "ANSWER is given, the candidate must be consistent with it in meaning.\n\n"
    "Reply with ONE JSON object and nothing else, exactly this shape:\n"
    '{{"verdict": "pass" | "fail", "score": <number between 0 and 1>, '
    '"reasoning": "<one short sentence>"}}\n\n'
    "INPUT:\n{input}\n\n"
    "{reference_section}"
    "CANDIDATE ANSWER:\n{output}\n"
)

_JUDGE_MODEL_VERSION = "judge-v1"


@dataclass(frozen=True, slots=True)
class _Verdict:
    passed: bool
    score: float


def render_judge_prompt(case_input: str, candidate_output: str, reference: str | None) -> str:
    """Assemble the rubric prompt. Pure function of its inputs."""
    reference_section = "" if reference is None else f"REFERENCE ANSWER:\n{reference}\n\n"
    return JUDGE_RUBRIC.format(
        input=case_input, output=candidate_output, reference_section=reference_section
    )


def parse_judge_verdict(text: str, *, evaluator: str) -> _Verdict:
    """Parse a judge reply into a verdict, or raise :class:`JudgeError`.

    Tolerates a single ``{...}`` object embedded in surrounding prose or a
    ```json fenced block; anything else -- non-JSON, wrong shape, an unknown
    verdict, a score outside ``[0, 1]`` -- is a hard failure.
    """
    obj = _extract_json_object(text)
    if obj is None:
        raise JudgeError(
            f"evaluator {evaluator!r}: judge reply is not a JSON object: {_snippet(text)}"
        )

    verdict = obj.get("verdict")
    if not isinstance(verdict, str) or verdict.strip().lower() not in {"pass", "fail"}:
        raise JudgeError(
            f"evaluator {evaluator!r}: judge 'verdict' must be 'pass' or 'fail', got {verdict!r}"
        )
    passed = verdict.strip().lower() == "pass"

    raw_score = obj.get("score")
    if raw_score is None:
        score = 1.0 if passed else 0.0
    elif isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
        raise JudgeError(
            f"evaluator {evaluator!r}: judge 'score' must be a number, got {raw_score!r}"
        )
    elif not 0.0 <= float(raw_score) <= 1.0:
        raise JudgeError(
            f"evaluator {evaluator!r}: judge 'score' must be within [0, 1], got {raw_score!r}"
        )
    else:
        score = float(raw_score)

    return _Verdict(passed=passed, score=score)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    candidate = text.strip()
    if candidate.startswith("```"):
        # strip a leading ```json / ``` fence and its closing counterpart
        candidate = candidate.split("```", 2)[1] if candidate.count("```") >= 2 else candidate
        if candidate.lstrip().lower().startswith("json"):
            candidate = candidate.lstrip()[4:]
        candidate = candidate.strip()
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        parsed = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _snippet(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= 120 else flat[:120] + "..."


@dataclass(frozen=True, slots=True)
class LLMJudge:
    """An ``Evaluator`` backed by a judge ``ProviderClient``.

    ``provider_name`` + ``provider_client`` are the judge's own model, entirely
    separate from the ``SystemVersion`` being evaluated. ``temperature`` is
    forced low by default for reproducibility.
    """

    provider_name: ProviderName
    provider_client: ProviderClient
    model: str
    temperature: float = 0.0
    name: str = "llm_judge"

    family: ClassVar[EvaluatorFamily] = EvaluatorFamily.LLM_JUDGE

    def evaluate(self, run: EvaluationRun, reference: DatasetCase) -> EvaluatorScore:
        prompt = render_judge_prompt(reference.input, run.output, reference.expected_output)
        judge_config = SystemVersion(
            project_id="judge",
            name=self.name,
            version=_JUDGE_MODEL_VERSION,
            provider=self.provider_name,
            model=self.model,
            prompt_template="${input}",
            parameters={"temperature": self.temperature},
        )
        # A ProviderError here propagates untouched (judge provider failure).
        response = self.provider_client.complete(prompt, judge_config)
        verdict = parse_judge_verdict(response.text, evaluator=self.name)
        return EvaluatorScore(
            evaluator=self.name,
            family=EvaluatorFamily.LLM_JUDGE,
            score=verdict.score,
            passed=verdict.passed,
        )

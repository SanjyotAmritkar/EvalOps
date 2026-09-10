"""Deterministic RAG evaluators (Phase 9, CP 9.1).

Score retrieval quality and answer grounding from the retrieval evidence an
external RAG system reports on an ``EvaluationRun``. EvalOps performs no
retrieval, embedding, or indexing here -- these evaluators only read
``run.retrieval`` (a tuple of :class:`~evalops.domain.value_objects.RetrievedItem`)
and the ground-truth ``reference.expected_retrieval_ids``.

Each is an ordinary ``Evaluator``: it emits an ``EvaluatorScore`` with the
graded metric in ``score`` (0..1) and a boolean ``passed`` from a configured
threshold, so its ``<name>.pass_rate`` metric flows through the existing
aggregation / paired-bootstrap evidence / release-gate path with **no**
RAG-specific handling anywhere downstream.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from evalops.domain.entities import DatasetCase, EvaluationRun
from evalops.domain.enums import EvaluatorFamily
from evalops.domain.value_objects import EvaluatorScore
from evalops.errors import ConfigError

#: What ``groundedness_lexical`` actually measures. Surfaced in the class
#: docstring, the config error path, and docs/ARCHITECTURE.md so nobody mistakes
#: it for a semantic or factual check.
LEXICAL_GROUNDEDNESS_NOTE = (
    "groundedness_lexical is a DETERMINISTIC LEXICAL APPROXIMATION: the fraction "
    "of the answer's distinct content words that also appear in the retrieved "
    "context. It measures lexical support, not semantic truth or factual "
    "correctness, and is NOT a hallucination detector -- a well-grounded "
    "paraphrase can score low and a copied-but-wrong answer can score high. Use "
    "it as a coarse regression signal alongside a reference-based or semantic "
    "evaluator."
)

#: Retrieval metrics are the Statistical/ML family per docs/ARCHITECTURE.md §6
#: ("retrieval metrics (Recall@K, Precision@K, MRR)"). The lexical groundedness
#: heuristic is a plain deterministic string operation.
_RETRIEVAL_FAMILY = EvaluatorFamily.STATISTICAL
_GROUNDEDNESS_FAMILY = EvaluatorFamily.DETERMINISTIC

_WORD_RE = re.compile(r"[a-z0-9]+")

#: A small, fixed function-word list. Deliberately tiny -- this is a coarse
#: overlap heuristic, not NLP.
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "this",
        "that",
        "these",
        "those",
        "and",
        "or",
        "but",
        "if",
        "then",
        "else",
        "of",
        "to",
        "in",
        "on",
        "at",
        "by",
        "for",
        "with",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "it",
        "its",
        "he",
        "she",
        "they",
        "them",
        "his",
        "her",
        "their",
        "you",
        "your",
        "we",
        "our",
        "i",
        "me",
        "my",
        "do",
        "does",
        "did",
        "not",
        "no",
        "yes",
        "can",
        "will",
        "would",
        "should",
        "could",
        "may",
        "might",
        "must",
        "have",
        "has",
        "had",
        "there",
        "here",
        "what",
        "which",
        "who",
        "whom",
        "whose",
        "than",
    }
)


def _unique_ordered(ids: Iterable[str]) -> list[str]:
    """De-duplicate ``ids`` keeping first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for value in ids:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _relevant_ids(reference: DatasetCase, evaluator_name: str) -> list[str]:
    """The case's ground-truth relevant ids, de-duplicated.

    Raises :class:`ConfigError` when the case has none -- EvalOps never
    fabricates relevance labels.
    """
    relevant = _unique_ordered(reference.expected_retrieval_ids)
    if not relevant:
        raise ConfigError(
            f"evaluator {evaluator_name!r} requires expected_retrieval_ids, "
            f"but case {reference.id!r} has none"
        )
    return relevant


def _retrieved_ids(run: EvaluationRun) -> list[str]:
    """Unique retrieved doc ids, in the order the system reported them."""
    return _unique_ordered(item.doc_id for item in run.retrieval)


def _content_tokens(text: str) -> set[str]:
    return {t for t in _WORD_RE.findall(text.lower()) if len(t) > 1 and t not in _STOPWORDS}


def _threshold(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0:
        raise ConfigError(f"{label} must be a number within [0, 1]")
    return float(value)


@dataclass(frozen=True, slots=True)
class RetrievalRecall:
    """``retrieval_recall = |relevant ∩ retrieved| / |relevant|`` over unique ids.

    * No expected relevant ids -> :class:`ConfigError` (labels are never faked).
    * No retrieved items -> recall ``0.0``.
    * Duplicate relevant or retrieved ids are collapsed before the ratio.
    * ``passed`` is ``recall >= min_recall`` (default ``1.0`` -- every relevant
      chunk must be retrieved).
    """

    min_recall: float = 1.0
    name: str = "retrieval_recall"

    family = _RETRIEVAL_FAMILY

    def __post_init__(self) -> None:
        _threshold(self.min_recall, f"evaluator {self.name!r} min_recall")

    def evaluate(self, run: EvaluationRun, reference: DatasetCase) -> EvaluatorScore:
        relevant = set(_relevant_ids(reference, self.name))
        retrieved = set(_retrieved_ids(run))
        recall = len(relevant & retrieved) / len(relevant)
        return EvaluatorScore(
            evaluator=self.name,
            family=self.family,
            score=recall,
            passed=recall >= self.min_recall,
        )


@dataclass(frozen=True, slots=True)
class ContextPrecision:
    """``context_precision = |relevant ∩ retrieved| / |retrieved|`` over unique ids.

    * No expected relevant ids -> :class:`ConfigError`.
    * **Zero denominator (nothing retrieved) -> ``0.0``.** Retrieving no context
      when known-relevant context exists is a retrieval failure, not perfect
      precision.
    * Duplicate retrieved ids are collapsed before the ratio.
    * ``passed`` is ``precision >= min_precision`` (default ``1.0`` -- every
      retrieved chunk must be relevant).
    """

    min_precision: float = 1.0
    name: str = "context_precision"

    family = _RETRIEVAL_FAMILY

    def __post_init__(self) -> None:
        _threshold(self.min_precision, f"evaluator {self.name!r} min_precision")

    def evaluate(self, run: EvaluationRun, reference: DatasetCase) -> EvaluatorScore:
        relevant = set(_relevant_ids(reference, self.name))
        retrieved = _retrieved_ids(run)
        if not retrieved:
            precision = 0.0
        else:
            precision = sum(1 for rid in retrieved if rid in relevant) / len(retrieved)
        return EvaluatorScore(
            evaluator=self.name,
            family=self.family,
            score=precision,
            passed=precision >= self.min_precision,
        )


@dataclass(frozen=True, slots=True)
class GroundednessLexical:
    """Deterministic lexical grounding approximation -- see
    :data:`LEXICAL_GROUNDEDNESS_NOTE`.

    ``score = |answer_content_words ∩ context_content_words| / |answer_content_words|``.

    * Empty / all-stopword answer -> ``1.0`` (vacuously grounded: it asserts
      nothing to support; a degenerate answer is caught by other metrics).
    * No retrieved context -> ``0.0`` for any non-trivial answer.
    * ``passed`` is ``score >= min_groundedness`` (default ``0.8``).

    This is **not** a hallucination detector and does not claim semantic or
    factual correctness.
    """

    min_groundedness: float = 0.8
    name: str = "groundedness_lexical"

    family = _GROUNDEDNESS_FAMILY

    def __post_init__(self) -> None:
        _threshold(self.min_groundedness, f"evaluator {self.name!r} min_groundedness")

    def evaluate(self, run: EvaluationRun, reference: DatasetCase) -> EvaluatorScore:
        answer_tokens = _content_tokens(run.output)
        if not answer_tokens:
            return EvaluatorScore(evaluator=self.name, family=self.family, score=1.0, passed=True)
        context_tokens = _content_tokens(" ".join(item.content for item in run.retrieval))
        grounded = len(answer_tokens & context_tokens) / len(answer_tokens)
        return EvaluatorScore(
            evaluator=self.name,
            family=self.family,
            score=grounded,
            passed=grounded >= self.min_groundedness,
        )


#: Config ``type`` -> whether every case needs ``expected_retrieval_ids``.
#: ``groundedness`` builds :class:`GroundednessLexical` (default result name
#: ``groundedness_lexical``); it compares answer vs retrieved context and needs
#: no relevance labels.
RAG_EVALUATOR_TYPES: dict[str, bool] = {
    "retrieval_recall": True,
    "context_precision": True,
    "groundedness": False,
}

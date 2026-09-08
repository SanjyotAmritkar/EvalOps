"""Tests for evalops.domain.enums."""

from __future__ import annotations

from enum import StrEnum

import pytest

from evalops.domain.enums import CaseOrigin, EvaluatorFamily, ProviderName, ReleaseDecision


def test_enum_wire_values_are_the_expected_strings() -> None:
    # These strings are a stored/serialized contract; a rename must be deliberate.
    assert [p.value for p in ProviderName] == ["openai", "anthropic", "ollama"]
    assert [f.value for f in EvaluatorFamily] == ["deterministic", "statistical", "llm_judge"]
    assert [o.value for o in CaseOrigin] == ["authored", "promoted_trace"]
    assert [d.value for d in ReleaseDecision] == ["pass", "block", "needs_review"]


@pytest.mark.parametrize("enum_cls", [ProviderName, EvaluatorFamily, CaseOrigin, ReleaseDecision])
def test_unknown_value_is_rejected(enum_cls: type[StrEnum]) -> None:
    with pytest.raises(ValueError):
        enum_cls("not-a-real-member")

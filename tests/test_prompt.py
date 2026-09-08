"""Tests for evalops.prompt.render_prompt."""

from __future__ import annotations

import pytest

from evalops.errors import ConfigError
from evalops.prompt import render_prompt


def test_braced_placeholder_is_substituted() -> None:
    assert render_prompt("Q: ${input}\nA:", "2 + 2") == "Q: 2 + 2\nA:"


def test_bare_placeholder_is_substituted() -> None:
    assert render_prompt("Q: $input!", "hi") == "Q: hi!"


def test_double_dollar_is_a_literal_dollar() -> None:
    assert render_prompt("Cost is $$5 for ${input}", "x") == "Cost is $5 for x"


def test_input_value_is_inserted_verbatim() -> None:
    # The substituted value is not re-scanned for placeholders.
    assert render_prompt("${input}", "$input and ${input}") == "$input and ${input}"


def test_missing_placeholder_is_rejected() -> None:
    with pytest.raises(ConfigError, match=r"must reference \$\{input\}"):
        render_prompt("no placeholder here", "x")


def test_unsupported_placeholder_is_rejected() -> None:
    with pytest.raises(ConfigError, match="unsupported placeholder"):
        render_prompt("${input} for ${model}", "x")


def test_malformed_dollar_syntax_is_rejected() -> None:
    with pytest.raises(ConfigError, match=r"invalid \$ syntax"):
        render_prompt("price $5 and ${input}", "x")


def test_lone_dollar_is_rejected() -> None:
    with pytest.raises(ConfigError, match=r"invalid \$ syntax"):
        render_prompt("lone $ then ${input}", "x")

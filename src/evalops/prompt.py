"""Render a prompt template against a dataset case input.

The only supported substitution is ``${input}`` (equivalently ``$input``),
using :class:`string.Template`. Write ``$$`` for a literal dollar sign. This is
intentionally not a templating engine: no conditionals, loops, filters, or
additional variables.
"""

from __future__ import annotations

from string import Template

from evalops.errors import ConfigError

_INPUT = "input"


def render_prompt(template: str, case_input: str) -> str:
    """Return ``template`` with ``${input}`` replaced by ``case_input``.

    Raises :class:`~evalops.errors.ConfigError` if the template does not
    reference ``${input}``, references any other placeholder, or contains
    malformed ``$`` syntax (use ``$$`` for a literal ``$``).
    """
    compiled = Template(template)
    identifiers = set(compiled.get_identifiers())

    unsupported = sorted(identifiers - {_INPUT})
    if unsupported:
        raise ConfigError(
            f"prompt_template references unsupported placeholder(s) {unsupported}; "
            "only ${input} is supported"
        )
    if _INPUT not in identifiers:
        raise ConfigError("prompt_template must reference ${input}")

    try:
        return compiled.substitute({_INPUT: case_input})
    except (KeyError, ValueError) as exc:
        raise ConfigError(
            f"prompt_template has invalid $ syntax ({exc}); use $$ for a literal $"
        ) from exc

"""Load a JSONL evaluation dataset into the domain ``Dataset`` model.

One JSON object per non-blank line. Recognised keys:

- ``input`` -- required, non-empty string
- ``expected_output`` -- optional string
- ``id`` -- optional non-empty string, unique across the file; generated when absent

Every malformed, empty, or duplicate-id input raises :class:`ConfigError` with
the file path and 1-based line number.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evalops.domain.entities import Dataset, DatasetCase
from evalops.domain.enums import CaseOrigin
from evalops.domain.ids import new_id
from evalops.errors import ConfigError

_ALLOWED_KEYS = {"input", "expected_output", "id"}


def load_jsonl(path: str | Path, *, project_id: str, name: str | None = None) -> Dataset:
    """Read a JSONL file at ``path`` and return a ``Dataset`` of AUTHORED cases.

    ``name`` defaults to the file's stem. ``project_id`` is stored on the
    returned ``Dataset``.
    """
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read dataset file {file_path}: {exc}") from exc

    cases: list[DatasetCase] = []
    first_seen: dict[str, int] = {}
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        cases.append(_parse_line(line, lineno, file_path, first_seen))

    if not cases:
        raise ConfigError(f"dataset file {file_path} contains no cases")

    return Dataset(
        project_id=project_id,
        name=name or file_path.stem,
        version=1,
        cases=tuple(cases),
    )


def _parse_line(line: str, lineno: int, file_path: Path, first_seen: dict[str, int]) -> DatasetCase:
    where = f"{file_path}:{lineno}"
    try:
        obj: Any = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{where}: not valid JSON ({exc.msg})") from exc

    if not isinstance(obj, dict):
        raise ConfigError(f"{where}: expected a JSON object, got {type(obj).__name__}")

    unknown = sorted(set(obj) - _ALLOWED_KEYS)
    if unknown:
        raise ConfigError(f"{where}: unknown field(s) {unknown}; allowed: {sorted(_ALLOWED_KEYS)}")

    raw_input = obj.get("input")
    if not isinstance(raw_input, str) or not raw_input.strip():
        raise ConfigError(f"{where}: 'input' must be a non-empty string")

    expected = obj.get("expected_output")
    if expected is not None and not isinstance(expected, str):
        raise ConfigError(f"{where}: 'expected_output' must be a string when present")

    case_id = obj.get("id")
    if case_id is not None:
        if not isinstance(case_id, str) or not case_id.strip():
            raise ConfigError(f"{where}: 'id' must be a non-empty string when present")
        if case_id in first_seen:
            raise ConfigError(
                f"{where}: duplicate id {case_id!r} (first seen at line {first_seen[case_id]})"
            )
        first_seen[case_id] = lineno

    return DatasetCase(
        input=raw_input,
        expected_output=expected,
        origin=CaseOrigin.AUTHORED,
        id=case_id if isinstance(case_id, str) else new_id(),
    )

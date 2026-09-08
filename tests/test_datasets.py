"""Tests for evalops.datasets.load_jsonl."""

from __future__ import annotations

from pathlib import Path

import pytest

from evalops.datasets import load_jsonl
from evalops.domain.enums import CaseOrigin
from evalops.errors import ConfigError


def _write(tmp_path: Path, *lines: str, name: str = "cases.jsonl") -> Path:
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_loads_a_valid_dataset(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        '{"input": "2 + 2 = ?", "expected_output": "4"}',
        '{"input": "capital of France", "expected_output": "Paris", "id": "case-2"}',
        '{"input": "no reference here"}',
    )

    dataset = load_jsonl(path, project_id="proj-1")

    assert dataset.project_id == "proj-1"
    assert dataset.name == "cases"
    assert dataset.version == 1
    assert len(dataset.cases) == 3
    assert all(case.origin is CaseOrigin.AUTHORED for case in dataset.cases)
    assert dataset.cases[0].expected_output == "4"
    assert dataset.cases[1].id == "case-2"
    assert dataset.cases[2].expected_output is None
    assert len(dataset.cases[2].id) == 32  # generated


def test_name_override(tmp_path: Path) -> None:
    path = _write(tmp_path, '{"input": "x"}')

    dataset = load_jsonl(path, project_id="p", name="golden")

    assert dataset.name == "golden"


def test_blank_lines_are_skipped(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text('\n{"input": "a"}\n\n   \n{"input": "b"}\n', encoding="utf-8")

    dataset = load_jsonl(path, project_id="p")

    assert len(dataset.cases) == 2


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read dataset file"):
        load_jsonl(tmp_path / "nope.jsonl", project_id="p")


def test_empty_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text("\n   \n\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="contains no cases"):
        load_jsonl(path, project_id="p")


def test_invalid_json_reports_line_number(tmp_path: Path) -> None:
    path = _write(tmp_path, '{"input": "ok"}', "{not json}", '{"input": "ok"}')

    with pytest.raises(ConfigError, match=r":2: not valid JSON"):
        load_jsonl(path, project_id="p")


def test_non_object_line_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, '["input", "x"]')

    with pytest.raises(ConfigError, match="expected a JSON object"):
        load_jsonl(path, project_id="p")


def test_scalar_line_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, "42")

    with pytest.raises(ConfigError, match="expected a JSON object"):
        load_jsonl(path, project_id="p")


def test_unknown_field_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, '{"input": "x", "expexted_output": "y"}')

    with pytest.raises(ConfigError, match="unknown field"):
        load_jsonl(path, project_id="p")


@pytest.mark.parametrize("line", ['{"expected_output": "4"}', '{"input": "   "}', '{"input": 7}'])
def test_bad_input_is_rejected(tmp_path: Path, line: str) -> None:
    path = _write(tmp_path, line)

    with pytest.raises(ConfigError, match="'input' must be a non-empty string"):
        load_jsonl(path, project_id="p")


def test_non_string_expected_output_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, '{"input": "x", "expected_output": 4}')

    with pytest.raises(ConfigError, match="'expected_output' must be a string"):
        load_jsonl(path, project_id="p")


@pytest.mark.parametrize("bad_id", ["4", '""', '"   "'])
def test_bad_id_is_rejected(tmp_path: Path, bad_id: str) -> None:
    path = _write(tmp_path, f'{{"input": "x", "id": {bad_id}}}')

    with pytest.raises(ConfigError, match="'id' must be a non-empty string"):
        load_jsonl(path, project_id="p")


def test_duplicate_id_is_rejected(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        '{"input": "a", "id": "dup"}',
        '{"input": "b", "id": "dup"}',
    )

    with pytest.raises(ConfigError, match=r":2: duplicate id 'dup' \(first seen at line 1\)"):
        load_jsonl(path, project_id="p")

"""Tests for evalops.domain.ids."""

from __future__ import annotations

import uuid

from evalops.domain.ids import new_id


def test_new_id_is_a_uuid4_hex_string() -> None:
    value = new_id()

    assert isinstance(value, str)
    assert len(value) == 32
    # Parses as a UUID and round-trips to the same hex (i.e. it really is one).
    assert uuid.UUID(hex=value).hex == value


def test_new_id_values_are_distinct() -> None:
    ids = {new_id() for _ in range(100)}

    assert len(ids) == 100

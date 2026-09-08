"""Entity identifier type and generator."""

from __future__ import annotations

import uuid

EntityId = str
"""A string that identifies a domain entity (a 32-character UUID4 hex value)."""


def new_id() -> EntityId:
    """Return a fresh, unique entity identifier."""
    return uuid.uuid4().hex

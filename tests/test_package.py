"""Smoke tests for the ``evalops`` package skeleton.

These exist so CI has a real, honest check to run during repository
initialization. They assert only that the package is importable and exposes
a version string -- there is no product behavior to test yet.
"""

from __future__ import annotations

import evalops


def test_package_is_importable() -> None:
    assert evalops.__doc__ is not None


def test_version_is_a_nonempty_string() -> None:
    assert isinstance(evalops.__version__, str)
    assert evalops.__version__ != ""

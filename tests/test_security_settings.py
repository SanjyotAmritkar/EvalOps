"""SecuritySettings parsing + the production fail-fast check (CP 10.5)."""

from __future__ import annotations

import pytest

from evalops.security.settings import (
    ProductionConfigError,
    SecuritySettings,
    validate_production_config,
)


def test_api_key_is_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVALOPS_API_KEY", raising=False)
    assert SecuritySettings.from_env().api_key is None


def test_api_key_blank_string_is_treated_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVALOPS_API_KEY", "   ")
    assert SecuritySettings.from_env().api_key is None


def test_api_key_reads_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVALOPS_API_KEY", "s3cr3t")
    assert SecuritySettings.from_env().api_key == "s3cr3t"


def test_cors_origins_default_to_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVALOPS_CORS_ALLOWED_ORIGINS", raising=False)
    assert SecuritySettings.from_env().cors_allow_origins == ()


def test_cors_origins_are_split_and_trimmed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVALOPS_CORS_ALLOWED_ORIGINS", " https://a.example , https://b.example ,,")
    assert SecuritySettings.from_env().cors_allow_origins == (
        "https://a.example",
        "https://b.example",
    )


def test_production_without_api_key_fails_fast() -> None:
    security = SecuritySettings(api_key=None, cors_allow_origins=())
    with pytest.raises(ProductionConfigError, match="EVALOPS_API_KEY"):
        validate_production_config(environment="production", security=security)


def test_production_with_api_key_is_fine() -> None:
    security = SecuritySettings(api_key="k", cors_allow_origins=())
    validate_production_config(environment="production", security=security)  # no raise


def test_development_without_api_key_is_fine() -> None:
    security = SecuritySettings(api_key=None, cors_allow_origins=())
    validate_production_config(environment="development", security=security)  # no raise

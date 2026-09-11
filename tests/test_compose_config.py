"""Structural checks on the production-shaped Compose stack (CP 10.4).

Parses docker-compose.yml with PyYAML -- no Docker engine required, so this
runs in ordinary CI. It does not build or start anything; the real thing is
exercised manually (see the CP 10.4 report's full-stack E2E section). This
only guards against the stack silently regressing: a service disappearing, a
health check being dropped, or Postgres/Redis being republished to the host.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

COMPOSE_PATH = Path(__file__).resolve().parent.parent / "docker-compose.yml"


def _load() -> dict[str, Any]:
    with COMPOSE_PATH.open(encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    assert isinstance(doc, dict)
    return doc


def test_compose_file_parses_as_yaml() -> None:
    doc = _load()
    assert isinstance(doc, dict)
    assert "services" in doc


def test_every_expected_service_is_present() -> None:
    services = _load()["services"]
    assert set(services) == {"postgres", "redis", "migrate", "api", "worker", "dashboard"}


def test_postgres_has_a_named_persistent_volume() -> None:
    doc = _load()
    postgres = doc["services"]["postgres"]
    mounts = postgres.get("volumes", [])
    assert any(m.startswith("postgres_data:") for m in mounts), mounts
    assert "postgres_data" in doc.get("volumes", {})


def test_postgres_and_redis_are_not_published_to_the_host() -> None:
    # Security baseline: internal dependencies stay internal by default.
    services = _load()["services"]
    for name in ("postgres", "redis"):
        assert "ports" not in services[name], f"{name} must not publish a host port by default"


@pytest.mark.parametrize("name", ["postgres", "redis", "api", "worker", "dashboard"])
def test_long_running_services_declare_a_healthcheck(name: str) -> None:
    service = _load()["services"][name]
    assert "healthcheck" in service
    assert "test" in service["healthcheck"]


def test_migrate_is_a_one_shot_job_not_restarted() -> None:
    migrate = _load()["services"]["migrate"]
    assert migrate["restart"] == "no"
    assert "healthcheck" not in migrate  # it runs once and exits; nothing to poll


def test_api_and_worker_wait_for_migrations_to_complete_and_redis_to_be_healthy() -> None:
    services = _load()["services"]
    for name in ("api", "worker"):
        depends_on = services[name]["depends_on"]
        assert depends_on["migrate"]["condition"] == "service_completed_successfully"
        assert depends_on["redis"]["condition"] == "service_healthy"


def test_migrate_waits_for_postgres_to_be_healthy() -> None:
    depends_on = _load()["services"]["migrate"]["depends_on"]
    assert depends_on["postgres"]["condition"] == "service_healthy"


def test_dashboard_waits_for_a_ready_api() -> None:
    depends_on = _load()["services"]["dashboard"]["depends_on"]
    assert depends_on["api"]["condition"] == "service_healthy"


def test_long_running_services_restart_unless_stopped() -> None:
    services = _load()["services"]
    for name in ("postgres", "redis", "api", "worker", "dashboard"):
        assert services[name]["restart"] == "unless-stopped"


def test_no_privileged_containers_or_docker_socket_mounts() -> None:
    doc = _load()
    dumped = yaml.safe_dump(doc)
    assert "privileged" not in dumped
    assert "docker.sock" not in dumped


def test_no_secret_is_hard_coded_as_a_literal_value() -> None:
    # Provider keys must flow through `${VAR}` substitution, never a literal.
    doc = _load()
    for service in doc["services"].values():
        env = service.get("environment", {})
        for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
            if key in env:
                assert str(env[key]).startswith("${"), f"{key} must not be a literal value"

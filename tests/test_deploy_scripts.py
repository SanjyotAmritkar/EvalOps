"""Structural + syntax validation for deploy/azure/*.sh (Phase 10, CP 10.5).

Hermetic -- no network call, no Azure command, no GitHub API call. `bash -n`
checks every script parses; `shellcheck` (only when already installed) lints
every script. The remaining checks are a regression guard for the OIDC
subject bug this cleanup fixed: GitHub's Environment-scoped OIDC subject is
``repo:<owner>@<owner_id>/<repo>@<repo_id>:environment:<name>`` -- the
``@<id>`` suffixes are GitHub's own immutable numeric IDs. A name-only
subject (``repo:<owner>/<repo>:environment:<name>``) silently never matches
what GitHub actually sends, so the federated credential never authenticates.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

DEPLOY_DIR = Path(__file__).resolve().parent.parent / "deploy" / "azure"
SCRIPTS = sorted(DEPLOY_DIR.glob("*.sh"))


def _read(name: str) -> str:
    return (DEPLOY_DIR / name).read_text(encoding="utf-8")


def test_deploy_scripts_exist() -> None:
    # Guards the glob above against a typo'd path silently matching nothing.
    assert SCRIPTS, f"no *.sh scripts found under {DEPLOY_DIR}"


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_script_has_valid_bash_syntax(script: Path) -> None:
    result = subprocess.run(
        ["bash", "-n", str(script)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck not installed")
@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_script_is_shellcheck_clean(script: Path) -> None:
    # cwd=DEPLOY_DIR so `-x` can actually resolve each script's `source
    # ./lib.sh` -- run from elsewhere, shellcheck can't follow it and (unable
    # to see lib.sh's `set -euo pipefail`) raises an unrelated SC2164 on the
    # `cd` line above it. Same reason every script itself does `cd
    # "$(dirname "${BASH_SOURCE[0]}")"` before sourcing lib.sh.
    result = subprocess.run(
        ["shellcheck", "-x", script.name],
        cwd=DEPLOY_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_oidc_subject_is_built_from_immutable_owner_and_repo_ids() -> None:
    source = _read("03-github-oidc.sh")
    assert re.search(
        r'OIDC_SUBJECT="repo:\$\{GITHUB_ORG\}@\$\{GITHUB_OWNER_ID\}'
        r'/\$\{GITHUB_REPO\}@\$\{GITHUB_REPO_ID\}:environment:production"',
        source,
    ), "the OIDC subject must include GitHub's immutable owner/repo IDs, not names alone"


def test_oidc_subject_no_longer_uses_the_name_only_form() -> None:
    source = _read("03-github-oidc.sh")
    buggy = "repo:${GITHUB_ORG}/${GITHUB_REPO}:environment:production"
    assert buggy not in source, "the legacy name-only subject must not reappear"


def test_owner_and_repo_ids_are_resolved_from_the_github_api_not_hard_coded() -> None:
    source = _read("03-github-oidc.sh")
    assert "api.github.com/repos/${GITHUB_ORG}/${GITHUB_REPO}" in source
    assert "GITHUB_OWNER_ID" in source and "GITHUB_REPO_ID" in source
    # No literal numeric GitHub id (this repo's or anyone else's) baked in.
    assert not re.search(r"@\d{5,}", source), "a real numeric GitHub id must never be hard-coded"


def test_ids_are_validated_as_numeric_before_use() -> None:
    source = _read("03-github-oidc.sh")
    assert source.count(r"^[0-9]+$") >= 2, (
        "both resolved ids should be checked as numeric before building the subject"
    )


def test_federated_credential_is_created_or_updated_when_stale_not_just_skipped() -> None:
    source = _read("03-github-oidc.sh")
    assert "federated-credential create" in source
    assert "federated-credential update" in source
    assert "CURRENT_SUBJECT" in source, "must compare the existing subject, not blindly skip"
    # The create and the staleness-comparison/update both key off one
    # computed subject -- not two independently-typed literals that could
    # drift apart.
    assert source.count("$OIDC_SUBJECT") >= 3


def test_generated_secrets_directory_is_gitignored() -> None:
    # 00/01/04 all write generated secrets (Postgres password, EVALOPS_API_KEY)
    # under ./.secrets/ and every comment says it is git-ignored -- it must
    # actually be, or a stray `git add .` could commit a real secret.
    gitignore = (DEPLOY_DIR / ".gitignore").read_text(encoding="utf-8")
    assert ".secrets/" in gitignore or ".secrets" in gitignore
    assert "config.env" in gitignore

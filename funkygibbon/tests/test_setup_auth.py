"""Tests for `funkygibbon.setup_auth` — the auth setup/migration tool.

Covers the .env upsert helpers, idempotency, secret/token rotation, and that the
minted client token actually verifies against the persisted JWT secret.
"""

from pathlib import Path

import pytest

from funkygibbon import setup_auth
from funkygibbon.auth import TokenManager


def test_upsert_preserves_comments_and_edits_in_place(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# header comment\nDATABASE_URL=sqlite:///x.db\nJWT_SECRET=old\n")
    new = setup_auth.upsert_env(env, {"JWT_SECRET": "new", "ADMIN_PASSWORD_HASH": "h"})
    env.write_text(new)
    parsed = setup_auth.read_env(env)
    assert "# header comment" in new           # comment preserved
    assert parsed["DATABASE_URL"] == "sqlite:///x.db"  # untouched
    assert parsed["JWT_SECRET"] == "new"        # edited in place
    assert parsed["ADMIN_PASSWORD_HASH"] == "h"  # appended
    assert new.count("JWT_SECRET=") == 1         # not duplicated


def _run(tmp_path, *extra):
    env = tmp_path / ".env"
    setup_auth.run([
        "--env-file", str(env), "--no-client-config", *extra,
    ])
    return setup_auth.read_env(env)


def test_test_mode_writes_managed_keys_and_working_token(tmp_path):
    cfg = _run(tmp_path, "--test-mode", "--test-password", "letmein")
    assert cfg["FUNKYGIBBON_TEST_MODE"] == "true"
    assert cfg["FUNKYGIBBON_TEST_PASSWORD"] == "letmein"
    assert cfg["ADMIN_PASSWORD_HASH"] == ""
    assert cfg["JWT_SECRET"]
    # The minted token must verify against the persisted secret as an admin.
    payload = TokenManager(secret_key=cfg["JWT_SECRET"]).verify_token(
        cfg["FUNKYGIBBON_CLIENT_TOKEN"]
    )
    assert payload and payload["role"] == "admin"


def test_idempotent_rerun_keeps_secret_and_token(tmp_path):
    first = _run(tmp_path, "--test-mode")
    second = _run(tmp_path, "--test-mode")
    assert second["JWT_SECRET"] == first["JWT_SECRET"]
    assert second["FUNKYGIBBON_CLIENT_TOKEN"] == first["FUNKYGIBBON_CLIENT_TOKEN"]


def test_rotate_secret_changes_secret_and_remints_token(tmp_path):
    first = _run(tmp_path, "--test-mode")
    rotated = _run(tmp_path, "--test-mode", "--rotate-secret")
    assert rotated["JWT_SECRET"] != first["JWT_SECRET"]
    assert rotated["FUNKYGIBBON_CLIENT_TOKEN"] != first["FUNKYGIBBON_CLIENT_TOKEN"]
    # Old token no longer verifies under the new secret.
    assert TokenManager(secret_key=rotated["JWT_SECRET"]).verify_token(
        first["FUNKYGIBBON_CLIENT_TOKEN"]
    ) is None


def test_admin_password_mode_hashes_and_disables_test_mode(tmp_path):
    cfg = _run(tmp_path, "--admin-password", "CorrectHorse9!xZ")
    assert cfg["ADMIN_PASSWORD_HASH"].startswith("$argon2")
    assert cfg["FUNKYGIBBON_TEST_MODE"] == "false"


def test_dry_run_writes_nothing(tmp_path):
    env = tmp_path / ".env"
    setup_auth.run(["--env-file", str(env), "--no-client-config", "--test-mode", "--dry-run"])
    assert not env.exists()

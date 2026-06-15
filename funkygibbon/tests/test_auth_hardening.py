"""Regression tests for auth hardening: no silent backdoor, fail-closed secrets,
explicit test mode. Auth modes resolve at import time, so each case runs in a
fresh subprocess with controlled environment."""

import os
import subprocess
import sys
import tempfile
import textwrap

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PP = os.pathsep.join([os.path.join(_REPO, "inbetweenies"), os.path.join(_REPO, "funkygibbon")])
_MODE_VARS = ("FUNKYGIBBON_TEST_MODE", "FUNKYGIBBON_TEST_PASSWORD", "JWT_SECRET",
              "SECRET_KEY", "ADMIN_PASSWORD_HASH")


def _run(env_extra, code):
    env = {k: v for k, v in os.environ.items() if k not in _MODE_VARS}
    env["PYTHONPATH"] = _PP
    env.update(env_extra)
    return subprocess.run([sys.executable, "-c", textwrap.dedent(code)],
                          env=env, capture_output=True, text=True)


def test_fail_closed_without_secret_or_test_mode():
    """No JWT secret and no test mode → the auth module refuses to load."""
    r = _run({}, "import funkygibbon.api.routers.auth")
    assert r.returncode != 0
    assert "No JWT signing secret" in (r.stderr + r.stdout)


def test_no_silent_admin_backdoor_and_configured_test_password_works():
    """In test mode a *configured* password grants admin; the old literal
    'admin' backdoor no longer works unless it IS the configured password."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = f.name
    try:
        code = """
            from funkygibbon.api.app import create_app
            from fastapi.testclient import TestClient
            c = TestClient(create_app())
            ok = c.post('/api/v1/auth/admin/login', json={'password': 's3cret-test-pw'}).status_code
            backdoor = c.post('/api/v1/auth/admin/login', json={'password': 'admin'}).status_code
            print('RESULT', ok, backdoor)
        """
        r = _run({"FUNKYGIBBON_TEST_MODE": "true",
                  "FUNKYGIBBON_TEST_PASSWORD": "s3cret-test-pw",
                  "FUNKYGIBBON_DB": db,
                  "DATABASE_URL": f"sqlite+aiosqlite:///{db}"}, code)
        assert "RESULT 200 401" in r.stdout, r.stdout + r.stderr
    finally:
        os.unlink(db)

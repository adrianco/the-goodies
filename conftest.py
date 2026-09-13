"""Repo-root pytest configuration.

Owns the *single* FunkyGibbon server that every integration test in this
repository shares (``blowing-off/tests``, ``funkygibbon/tests`` and the
top-level ``tests``). Living at the repo root means one server process per
pytest session instead of one per sub-project fixture.

WHY THIS EXISTS (the bug it fixes)
----------------------------------
The previous fixture (blowing-off/tests/conftest.py) started the server on the
hardcoded port 8000 and then "checked readiness" with ``GET
localhost:8000/health``. That check cannot tell "my server came up" apart from
"somebody else's server was already listening there". On a machine where port
8000 was already taken, the fixture's own subprocess died on bind, the health
probe was answered by the *stranger's* server, the fixture declared success and
every integration test then ran against the wrong server (and got 401s).

The harness below removes both halves of that failure mode:

* the server is started on a **freshly allocated ephemeral port**, never 8000;
* readiness is only accepted once we have **proved the responder is ours** --
  our subprocess is still alive, and the responder accepts an admin password
  and issues a JWT that only a server sharing our secrets could issue.

If the subprocess dies at any point during startup the fixture fails loudly
with the server's captured stderr. It never falls through to another server.

SERVER OUTPUT GOES TO A FILE, NEVER A PIPE
-----------------------------------------
The subprocess writes stdout+stderr to ``<work_dir>/server.log``. This is not a
style preference. ``subprocess.PIPE`` with no reader deadlocks the child once
the OS pipe buffer (64 KiB) fills, and this server writes an audit record per
authenticated request -- so the suite worked right up until it made enough
requests, and then the server simply stopped serving mid-run. The symptom was
maddening: ``/health`` answering in a millisecond while the very next
``/api/v1/sync/`` hung past every timeout, because the buffer filled between
the two. It presented as a flaky test in whichever module happened to follow,
and adding *any* module that talked to the server brought it forward, so the
blame always landed on the newest test rather than on the harness.

AUTHENTICATION
--------------
Tests exercise the real auth path rather than bypassing it: the server is
started with a real Argon2 ``ADMIN_PASSWORD_HASH`` and a real ``JWT_SECRET``
(``FUNKYGIBBON_TEST_MODE`` is explicitly *off*), and the ``auth_token`` fixture
is a genuine JWT obtained by POSTing to ``/api/v1/auth/admin/login``.
"""

import os
import socket
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).parent.resolve()

# Password used for the test server's admin account. Shared with
# tests/test_e2e_with_security.py, which authenticates with it directly.
# Must satisfy PasswordManager.check_password_strength().
TEST_ADMIN_PASSWORD = "TestAdmin#2024!"

# Signing secret for the test server. Must NOT be one of the values funkygibbon
# treats as insecure (see funkygibbon/api/routers/auth.py::_INSECURE_SECRETS),
# otherwise the server refuses to start without FUNKYGIBBON_TEST_MODE.
TEST_JWT_SECRET = "funkygibbon-integration-test-signing-secret-6b1f9c2e"

# The port owned by whatever else may be running on this machine. The harness
# must never bind it, probe it, or hand it to a test.
FORBIDDEN_PORT = 8000

SERVER_START_TIMEOUT = 60.0  # seconds; includes DB init on a cold temp database


def _find_free_port() -> int:
    """Ask the OS for an unused TCP port on the loopback interface."""
    for _ in range(20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        if port != FORBIDDEN_PORT:
            return port
    raise RuntimeError("Could not allocate a free ephemeral port")


def _drain(process: subprocess.Popen, log_path: "Path | None" = None) -> str:
    """Best-effort capture of a dead/dying server's output, for diagnostics.

    Reads the log FILE the server writes to. It used to call
    `process.communicate()` to drain the pipes -- which is also the only thing
    that ever emptied them, and it only ran on the failure path. On the happy
    path the pipes were never read at all, so the server deadlocked on a full
    buffer once the suite made enough requests. See the fixture below.
    """
    if process.poll() is None:
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
    if log_path is None or not Path(log_path).exists():
        return "--- server output unavailable ---"
    return f"--- server output ---\n{Path(log_path).read_text()[-8000:]}"


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


class _ServerStartupError(RuntimeError):
    """Raised when our server subprocess did not come up. Always fatal."""


def _await_health(process: subprocess.Popen, base_url: str,
                  log_path: "Path | None" = None) -> None:
    """Block until *our* server answers /health, or raise.

    ``process.poll()`` is re-checked on every attempt: if the subprocess has
    exited we fail immediately with its output instead of continuing to poll a
    port that some other process might answer.
    """
    import time

    deadline = time.monotonic() + SERVER_START_TIMEOUT
    last_error = "no response"

    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise _ServerStartupError(
                f"FunkyGibbon test server exited with code {process.returncode} "
                f"before becoming ready.\n{_drain(process, log_path)}"
            )
        try:
            response = httpx.get(f"{base_url}/health", timeout=2.0)
            if response.status_code == 200 and response.json().get("status") == "healthy":
                return
            last_error = f"HTTP {response.status_code}: {response.text[:200]}"
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(0.25)

    _stop(process)
    raise _ServerStartupError(
        f"FunkyGibbon test server at {base_url} was not healthy within "
        f"{SERVER_START_TIMEOUT:.0f}s (last: {last_error}).\n{_drain(process, log_path)}"
    )


def _login(base_url: str, password: str) -> str:
    """Obtain a real admin JWT. Doubles as proof of server identity.

    Only a server started with *our* Argon2 hash accepts this password, and
    only a server holding *our* JWT secret can mint a token that
    ``/api/v1/auth/me`` will then accept. A stranger's server on a stray port
    could not satisfy both.
    """
    response = httpx.post(
        f"{base_url}/api/v1/auth/admin/login",
        json={"password": password},
        timeout=10.0,
    )
    if response.status_code != 200:
        raise _ServerStartupError(
            f"Admin login against {base_url} failed with HTTP "
            f"{response.status_code}: {response.text[:500]}. The server on this "
            f"port is not the one this fixture started."
        )
    token = response.json()["access_token"]

    whoami = httpx.get(
        f"{base_url}/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    )
    if whoami.status_code != 200 or whoami.json().get("role") != "admin":
        raise _ServerStartupError(
            f"Server at {base_url} did not honour the token it just issued "
            f"(HTTP {whoami.status_code}: {whoami.text[:300]}). Refusing to run "
            f"tests against it."
        )
    return token


@pytest.fixture(scope="session")
def funkygibbon_admin_password() -> str:
    """The admin password the test server is configured to accept."""
    return TEST_ADMIN_PASSWORD


class RunningServer:
    """A FunkyGibbon subprocess this harness started, and how to reach it."""

    def __init__(self, base_url, token, process, log_handle, work_dir):
        self.base_url, self.token = base_url, token
        self._process, self._log_handle, self._work_dir = process, log_handle, work_dir

    def stop(self) -> None:
        _stop(self._process)
        self._log_handle.close()
        shutil.rmtree(self._work_dir, ignore_errors=True)


def start_funkygibbon(admin_password: str, *, seed: "list[str] | None" = None,
                      env_extra: "dict[str, str] | None" = None) -> RunningServer:
    """Seed a fresh database and start a FunkyGibbon on a private port.

    ``seed`` is the argv of the script that populates the database (default:
    the house seed); ``env_extra`` is merged into the server's environment --
    a vehicles server passes ``DOMAIN_MANIFEST``. Shared by the session
    fixture below and by any test that needs a server of another domain
    (ADR-012: the same engine, a different manifest, a different database).
    """
    from funkygibbon.auth import PasswordManager

    work_dir = tempfile.mkdtemp(prefix="funkygibbon-test-")
    db_path = os.path.join(work_dir, "test.db")
    port = _find_free_port()
    assert port != FORBIDDEN_PORT
    base_url = f"http://127.0.0.1:{port}"

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(REPO_ROOT)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    env["API_HOST"] = "127.0.0.1"
    env["API_PORT"] = str(port)
    # Real auth, not a bypass: an Argon2 hash of a known password plus a real
    # signing secret. FUNKYGIBBON_TEST_MODE stays off so the production code
    # path (hash verification) is what the tests exercise.
    env["ADMIN_PASSWORD_HASH"] = PasswordManager().hash_password(admin_password)
    env["JWT_SECRET"] = TEST_JWT_SECRET
    env.pop("FUNKYGIBBON_TEST_MODE", None)
    env.pop("FUNKYGIBBON_TEST_PASSWORD", None)
    env.pop("SECRET_KEY", None)
    # Don't let the scheduled-backup thread write files during the test run.
    env["BACKUP_SCHEDULE_ENABLED"] = "false"
    env.update(env_extra or {})

    # Seed the database *before* the server opens it: population truncates and
    # rewrites the graph tables, which is safer without a live writer attached.
    # A failure here is fatal -- silently running the integration suite against
    # an empty graph is how "passing" tests stop meaning anything.
    seed_argv = seed or [sys.executable, str(REPO_ROOT / "funkygibbon" / "populate_graph_db.py")]
    populate = subprocess.run(seed_argv, cwd=work_dir, env=env, capture_output=True, text=True)
    if populate.returncode != 0:
        shutil.rmtree(work_dir, ignore_errors=True)
        pytest.fail(
            f"{' '.join(seed_argv)} failed to seed the test database "
            f"(exit {populate.returncode}).\n"
            f"--- stdout ---\n{populate.stdout}\n--- stderr ---\n{populate.stderr}"
        )

    # cwd is the throwaway work dir so the server's audit logs and any stray
    # .env pickup stay out of the repo.
    #
    # Output goes to a FILE, not to a pipe. `subprocess.PIPE` with nobody
    # reading it is a deadlock waiting for a slow enough test suite: the OS
    # pipe buffer is 64 KiB, and once it fills the server blocks on its next
    # write and simply stops serving. It logs an audit record per authenticated
    # request, so the failure mode was "the suite works until it does enough
    # requests" -- a health check answering in 1 ms while the very next
    # /api/v1/sync/ hung past every timeout, because the buffer happened to
    # fill between them. Adding any module that talked to the server brought it
    # forward; nothing about the added module was wrong.
    #
    # A file keeps the diagnostics `_drain` needs and cannot fill.
    log_path = Path(work_dir) / "server.log"
    log_handle = open(log_path, "w+")
    process = subprocess.Popen(
        [sys.executable, "-m", "funkygibbon"],
        cwd=work_dir,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )

    try:
        _await_health(process, base_url, log_path)
        token = _login(base_url, admin_password)
    except _ServerStartupError as exc:
        _stop(process)
        detail = _drain(process, log_path)
        log_handle.close()
        shutil.rmtree(work_dir, ignore_errors=True)
        pytest.fail(f"{exc}\n{detail}")

    return RunningServer(base_url, token, process, log_handle, work_dir)


@pytest.fixture(scope="session")
def funkygibbon_server(funkygibbon_admin_password):
    """Start a FunkyGibbon server on a private ephemeral port.

    Yields ``(base_url, admin_token)``. Prefer the ``server_url`` /
    ``auth_token`` fixtures in tests.
    """
    server = start_funkygibbon(funkygibbon_admin_password)
    print(f"\n✅ FunkyGibbon test server ready at {server.base_url}")
    try:
        yield server.base_url, server.token
    finally:
        server.stop()
        print(f"\n✅ FunkyGibbon test server on {server.base_url} stopped")


@pytest.fixture(scope="session")
def server_url(funkygibbon_server) -> str:
    """Base URL of the FunkyGibbon server started for this test session."""
    return funkygibbon_server[0]


@pytest.fixture(scope="session")
def auth_token(funkygibbon_server) -> str:
    """A genuine admin JWT issued by the test server."""
    return funkygibbon_server[1]


@pytest.fixture(scope="session")
def running_server(server_url) -> str:
    """Alias kept for funkygibbon/tests/integration/test_server_startup.py."""
    return server_url

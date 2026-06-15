"""Auth-enforcement tests for the data endpoints.

These prove that authentication is actually *attached* to the data routers, not
merely defined. Every protected endpoint must reject an unauthenticated request
(401/403) and a request bearing a bogus token (401), and must accept a request
carrying a valid bearer token (so wiring auth does not lock out legitimate local
use). They are designed to be RED before auth is wired in app.py and GREEN after.

A valid token is obtained through the real login flow: under FUNKYGIBBON_TEST_MODE
(set by the top-level conftest) `POST /auth/admin/login` with the configured test
password mints an admin JWT.
"""

import pytest

API = "/api/v1"

# Representative endpoints across every protected router. The point is coverage of
# each router (graph / mcp / sync / sync-metadata) and both reads and writes — a
# router-level dependency protects all of its routes, so one per router proves it.
PROTECTED = [
    ("GET", f"{API}/graph/entities"),
    ("GET", f"{API}/graph/statistics"),
    ("POST", f"{API}/graph/entities"),
    ("GET", f"{API}/mcp/tools"),
    ("GET", f"{API}/sync-metadata/"),
    ("POST", f"{API}/sync-metadata/"),
    ("GET", f"{API}/sync/status"),
    ("POST", f"{API}/sync/"),
]

# Endpoints that should return a clean 200 for an authenticated read against an
# empty test database (proves auth lets legitimate traffic through).
READABLE = [
    f"{API}/graph/entities",
    f"{API}/graph/statistics",
    f"{API}/mcp/tools",
    f"{API}/sync-metadata/",
]


async def _send(client, method, path, headers=None):
    if method == "GET":
        return await client.get(path, headers=headers)
    return await client.post(path, json={}, headers=headers)


@pytest.fixture
def bearer():
    """Build an Authorization header dict from a token string."""
    return lambda token: {"Authorization": f"Bearer {token}"}


async def _login(client):
    """Log in via the real admin login flow (test mode) and return the JWT."""
    resp = await client.post(
        f"{API}/auth/admin/login", json={"password": "admin"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", PROTECTED)
async def test_unauthenticated_request_is_rejected(async_client, method, path):
    """No Authorization header → the endpoint must refuse before doing any work."""
    resp = await _send(async_client, method, path)
    assert resp.status_code in (401, 403), (
        f"{method} {path} returned {resp.status_code}; expected 401/403 — "
        f"auth is not attached to this router"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", PROTECTED)
async def test_invalid_token_is_rejected(async_client, bearer, method, path):
    """A malformed/forged bearer token → 401 Invalid or expired token."""
    resp = await _send(async_client, method, path, headers=bearer("not-a-real-jwt"))
    assert resp.status_code == 401, (
        f"{method} {path} returned {resp.status_code} for a bogus token; expected 401"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", PROTECTED)
async def test_valid_token_passes_auth(async_client, bearer, method, path):
    """A valid bearer token must clear the auth gate (never 401/403)."""
    token = await _login(async_client)
    resp = await _send(async_client, method, path, headers=bearer(token))
    assert resp.status_code not in (401, 403), (
        f"{method} {path} returned {resp.status_code} WITH a valid token — "
        f"authenticated local use is being locked out"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("path", READABLE)
async def test_authenticated_read_succeeds(async_client, bearer, path):
    """Authenticated reads against an empty DB return 200, not just non-401."""
    token = await _login(async_client)
    resp = await async_client.get(path, headers=bearer(token))
    assert resp.status_code == 200, f"GET {path} -> {resp.status_code}: {resp.text}"

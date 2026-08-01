"""
Test configuration for Blowing-Off tests.

The FunkyGibbon server used by the integration tests is NOT started here any
more. It is owned by the repo-root conftest.py, which starts it on a freshly
allocated ephemeral port and proves the responder is its own subprocess before
handing out a URL.

The fixture that used to live here started the server on the hardcoded port
8000 and then probed http://localhost:8000/health to decide whether it had come
up. That probe cannot distinguish "my server started" from "some other server
was already listening on 8000", so on a machine where 8000 was taken the
fixture reported success while its own subprocess was dead, and every
integration test silently ran against a foreign server. See conftest.py at the
repo root for the replacement.

The `server_url` and `auth_token` fixtures are inherited from that root
conftest; nothing in this package should hardcode a host or port.

REVISION HISTORY:
- 2025-07-28: Fixed server startup to use module approach (python -m funkygibbon)
- 2026-07-31: Moved the server fixture to the repo-root conftest (ephemeral
  port + real auth token); removed the hardcoded port 8000.
"""

import asyncio
import sys
from pathlib import Path

import pytest


# Register pytest markers
def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )


# Put the repo ROOT on the path so `funkygibbon` / `inbetweenies` import as
# packages. Inserting the funkygibbon dir itself would expose funkygibbon/mcp as
# a top-level `mcp` and shadow the installed MCP SDK (mcp.server, mcp.types).
repo_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(repo_root))


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

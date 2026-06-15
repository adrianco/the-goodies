"""Minimal .env loader.

The auth router and several other modules read configuration via ``os.getenv``
at import time. Pydantic settings read ``.env`` for their own fields, but that
does not populate ``os.environ``, so plain ``os.getenv`` calls never see it.
This loads a ``.env`` file into the process environment early (from the package
``__init__``) so a ``.env`` written by ``setup-auth`` is picked up by the server.

Real environment variables always win: existing keys are never overwritten.
No third-party dependency (python-dotenv is not guaranteed to be installed).
"""

import os
from pathlib import Path


def load_env_file(path: str = ".env") -> None:
    """Load KEY=VALUE pairs from `path` into os.environ via setdefault.

    Silently does nothing if the file is absent. Lines that are blank, comments
    (`#`), or lack an `=` are skipped. Surrounding quotes on values are stripped.
    A leading `export ` is tolerated.
    """
    env_path = Path(path)
    if not env_path.is_file():
        return

    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)

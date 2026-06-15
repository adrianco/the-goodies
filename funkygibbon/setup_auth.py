#!/usr/bin/env python3
"""
FunkyGibbon - Authentication setup / migration

Run as:  python -m funkygibbon.setup_auth [options]

The installs historically ran with authentication unattached to the data
endpoints. Once auth is wired (every data endpoint requires a bearer token),
each install needs a one-time setup that:

  1. Generates and persists a strong JWT signing secret (JWT_SECRET) in .env,
     so tokens survive restarts. Re-running keeps the existing secret (so
     previously issued tokens stay valid) unless --rotate-secret is given.
  2. Configures *how* an admin authenticates — either a real admin password
     (argon2 hash stored as ADMIN_PASSWORD_HASH) or explicit, opt-in test mode
     (FUNKYGIBBON_TEST_MODE=true with a configured FUNKYGIBBON_TEST_PASSWORD).
  3. Mints a long-lived admin token and writes it into the local client configs
     (oook: ~/.oook/config.json, blowing-off: ./.blowingoff.json) so the CLIs
     keep working against the now-protected server.

It is idempotent and supports --dry-run. Rollback is simply restoring the prior
.env / client config (or disabling auth by clearing the relevant keys).

This script writes secrets to local files. It is intended for the trusted,
local, single-house deployment described in the project docs.
"""

import argparse
import json
import os
import secrets
import sys
from datetime import timedelta
from pathlib import Path
from typing import Dict, Optional

# Ensure the package is importable when run as a plain script too.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from funkygibbon.auth import PasswordManager, TokenManager  # noqa: E402

MANAGED_KEYS = (
    "JWT_SECRET",
    "ADMIN_PASSWORD_HASH",
    "FUNKYGIBBON_TEST_MODE",
    "FUNKYGIBBON_TEST_PASSWORD",
    "FUNKYGIBBON_CLIENT_TOKEN",
)


# --------------------------------------------------------------------------- #
# .env read / upsert (comment- and order-preserving)
# --------------------------------------------------------------------------- #
def read_env(path: Path) -> Dict[str, str]:
    """Parse an .env file into a dict (best effort; ignores comments/blanks)."""
    values: Dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def upsert_env(path: Path, updates: Dict[str, str]) -> str:
    """Return new .env text with `updates` applied: existing keys edited in
    place, new keys appended. Comments and unrelated lines are preserved."""
    lines = path.read_text().splitlines() if path.is_file() else []
    remaining = dict(updates)
    out = []
    for raw in lines:
        stripped = raw.strip()
        body = stripped[len("export "):] if stripped.startswith("export ") else stripped
        key = body.partition("=")[0].strip() if "=" in body else None
        if key and key in remaining:
            out.append(f"{key}={remaining.pop(key)}")
        else:
            out.append(raw)
    if remaining:
        if out and out[-1].strip():
            out.append("")
        out.append("# Added by funkygibbon setup-auth")
        for key, value in remaining.items():
            out.append(f"{key}={value}")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- #
# Client config writers
# --------------------------------------------------------------------------- #
def write_json_config(path: Path, updates: Dict[str, str], dry_run: bool) -> None:
    """Merge `updates` into a JSON config file, creating parents as needed."""
    existing: Dict[str, object] = {}
    if path.is_file():
        try:
            existing = json.loads(path.read_text())
        except ValueError:
            existing = {}
    existing.update(updates)
    rendered = json.dumps(existing, indent=2) + "\n"
    if dry_run:
        print(f"  [dry-run] would write {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    print(f"  wrote {path}")


# --------------------------------------------------------------------------- #
# Core
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m funkygibbon.setup_auth",
        description="Configure authentication for a FunkyGibbon install.",
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--admin-password", metavar="PASS",
                      help="Set a real admin password (argon2-hashed into .env).")
    mode.add_argument("--test-mode", action="store_true",
                      help="Enable explicit, opt-in test mode (a known test password).")
    mode.add_argument("--client-token-only", action="store_true",
                      help="Mint a client token from an EXISTING JWT secret and write "
                           "client configs, without changing any auth config. Use when "
                           "the server's secret lives outside .env (e.g. a launchd start "
                           "script): pass --jwt-secret or set JWT_SECRET.")
    p.add_argument("--jwt-secret", metavar="SECRET",
                   help="Existing JWT signing secret to mint the client token against "
                        "(with --client-token-only). Falls back to $JWT_SECRET / .env.")
    p.add_argument("--test-password", metavar="PASS", default="admin",
                   help="Password accepted in test mode (default: admin).")
    p.add_argument("--server-url", default="http://localhost:8000",
                   help="Server URL written into client configs.")
    p.add_argument("--token-days", type=int, default=3650,
                   help="Client token lifetime in days (default: 3650).")
    p.add_argument("--rotate-secret", action="store_true",
                   help="Regenerate JWT_SECRET (invalidates all existing tokens).")
    p.add_argument("--rotate-token", action="store_true",
                   help="Re-mint the client token even if one already exists.")
    p.add_argument("--env-file", default=".env", help="Path to .env (default: .env).")
    p.add_argument("--no-client-config", action="store_true",
                   help="Do not write oook / blowing-off client configs.")
    p.add_argument("--oook-config", default=os.path.expanduser("~/.oook/config.json"),
                   help="oook config path.")
    p.add_argument("--blowingoff-config", default=".blowingoff.json",
                   help="blowing-off config path.")
    p.add_argument("--print-token", action="store_true",
                   help="Print the client token to stdout.")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would change without writing anything.")
    return p


def run(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    env_path = Path(args.env_file)
    current = read_env(env_path)
    pm = PasswordManager()

    insecure = {"", "development-secret-key", "dev-secret-key-change-in-production"}

    # client-token-only: mint a token from an existing secret, touch no auth config.
    if args.client_token_only:
        secret = (args.jwt_secret or os.getenv("JWT_SECRET")
                  or current.get("JWT_SECRET", "")).strip()
        if secret in insecure:
            print("error: no usable JWT secret — pass --jwt-secret or set JWT_SECRET "
                  "to the secret the server actually signs with.", file=sys.stderr)
            return 1
        token = TokenManager(secret_key=secret).create_token(
            user_id="local-client", role="admin",
            permissions=["read", "write", "delete", "configure"],
            expires_delta=timedelta(days=args.token_days),
        )
        print("FunkyGibbon client-token setup")
        print(f"  client token: minted ({args.token_days}d) against the existing secret")
        if args.print_token:
            print(f"  TOKEN: {token}")
        if not args.no_client_config:
            print("client configs:")
            write_json_config(Path(args.oook_config),
                              {"server_url": args.server_url, "auth_token": token},
                              args.dry_run)
            write_json_config(Path(args.blowingoff_config),
                              {"server_url": args.server_url, "auth_token": token,
                               "client_id": "local", "db_path": "blowingoff.db"},
                              args.dry_run)
        return 0

    updates: Dict[str, str] = {}

    # 1. JWT secret -------------------------------------------------------- #
    secret = current.get("JWT_SECRET", "").strip()
    if args.rotate_secret or secret in insecure:
        secret = secrets.token_urlsafe(48)
        updates["JWT_SECRET"] = secret
        secret_action = "rotated" if args.rotate_secret else "generated"
    else:
        secret_action = "kept existing"

    # 2. Auth mode --------------------------------------------------------- #
    if args.test_mode:
        updates["FUNKYGIBBON_TEST_MODE"] = "true"
        updates["FUNKYGIBBON_TEST_PASSWORD"] = args.test_password
        # Test-mode admin login only triggers when no hash is configured.
        updates["ADMIN_PASSWORD_HASH"] = ""
        mode_desc = f"test mode (password: {args.test_password!r})"
    else:
        strong, message = pm.check_password_strength(args.admin_password)
        if not strong:
            print(f"⚠ weak admin password: {message} (continuing anyway)", file=sys.stderr)
        updates["ADMIN_PASSWORD_HASH"] = pm.hash_password(args.admin_password)
        updates["FUNKYGIBBON_TEST_MODE"] = "false"
        mode_desc = "admin password (argon2 hash)"

    # 3. Client token ------------------------------------------------------ #
    existing_token = current.get("FUNKYGIBBON_CLIENT_TOKEN", "").strip()
    must_remint = args.rotate_token or args.rotate_secret or not existing_token
    if must_remint:
        token = TokenManager(secret_key=secret).create_token(
            user_id="local-client",
            role="admin",
            permissions=["read", "write", "delete", "configure"],
            expires_delta=timedelta(days=args.token_days),
        )
        updates["FUNKYGIBBON_CLIENT_TOKEN"] = token
        token_action = f"minted ({args.token_days}d)"
    else:
        token = existing_token
        token_action = "kept existing"

    # --- Report + write --------------------------------------------------- #
    print("FunkyGibbon auth setup")
    print(f"  env file:     {env_path}")
    print(f"  JWT secret:   {secret_action}")
    print(f"  auth mode:    {mode_desc}")
    print(f"  client token: {token_action}")
    if args.print_token:
        print(f"  TOKEN: {token}")

    new_env = upsert_env(env_path, updates)
    if args.dry_run:
        print("\n[dry-run] .env would become:\n")
        print("\n".join("    " + ln for ln in new_env.splitlines()))
    else:
        env_path.write_text(new_env)
        try:
            os.chmod(env_path, 0o600)
        except OSError:
            pass
        print(f"  wrote {env_path}")

    if not args.no_client_config:
        print("client configs:")
        write_json_config(Path(args.oook_config),
                          {"server_url": args.server_url, "auth_token": token},
                          args.dry_run)
        write_json_config(Path(args.blowingoff_config),
                          {"server_url": args.server_url, "auth_token": token,
                           "client_id": "local", "db_path": "blowingoff.db"},
                          args.dry_run)

    print("\nNext: (re)start the server so it picks up .env, then verify:")
    print(f"  curl -s -o /dev/null -w '%{{http_code}}' {args.server_url}/api/v1/graph/statistics   # expect 401/403")
    print(f"  curl -s -o /dev/null -w '%{{http_code}}' -H 'Authorization: Bearer <token>' "
          f"{args.server_url}/api/v1/graph/statistics   # expect 200")
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()

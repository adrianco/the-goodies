# ADR-020: Secrets and tokens — the Keychain holds credentials, files do not

**Status:** Proposed · 2026-09-23 · Companion to ADR-019; the parts that
concern the Python tooling (§2, §4) can land independently of the helper.

## Context

Where credentials live today, on a real install:

| Credential | Lives in | Mode |
|---|---|---|
| Server `JWT_SECRET` and `ADMIN_PASSWORD_HASH` | `start_funkygibbon.sh`, exported into the launchd environment | file, 700 |
| Client token (oook) | `~/.oook/config.json` | plaintext JSON |
| Client token (blowing-off) | `./.blowingoff.json` in the checkout | plaintext JSON |
| Client token (KittenKong, skills) | `FUNKYGIBBON_TOKEN` in an MCP config / shell env, or read from the files above | plaintext |
| Second-domain server secret | `~/.funkygibbon/<domain>/start_funkygibbon_<domain>.sh` (ADR-018) | file, 700 |
| Home Assistant, UniFi, review-page tokens | environment variables | plaintext |

Every one of these is a plaintext file or environment variable, readable by
any process running as the user, present in shell history when set, and
copied by any backup of the home directory. The client token is a
**long-lived write credential** to the whole graph. It was minted this way
because the clients are Python and TypeScript scripts, for which a JSON file
is the path of least resistance — and because until ADR-019 there was no
component on the Mac that could do better.

macOS has a credential store with exactly the properties wanted: per-item
access control, encryption at rest under the login password, an audit trail
of which process read what, and Touch ID / password prompts for the
sensitive items. Nothing in the system uses it.

## Decision

### 1. Client tokens live in the Keychain

A client token is a Keychain generic-password item, service
`com.the-goodies.funkygibbon`, account `<domain>@<server-url>` (one per
domain endpoint per host, ADR-018). It is written once by whoever mints it
and read by every client on that Mac:

- `setup_auth --client-token-only` writes it (via the `security` CLI on
  macOS; the JSON files remain the fallback on Linux, and `--no-keychain`
  keeps them on macOS for anyone who wants that).
- `fg_client.py`, oook and blowing-off look in the Keychain **first**, then
  `FUNKYGIBBON_TOKEN`, then the files — and print a one-line deprecation
  notice when they fall through to a file.
- KittenKong's MCP config stops carrying the token: the server launched by
  Claude reads it from the Keychain through a small helper (`security
  find-generic-password`), so a config file that gets synced or shared never
  contains a credential.
- ADR-019's helper reads and holds it through the `Security` framework with
  an access-control list naming its own bundle; the Python tools' reads
  prompt once per binary, which is the audit trail working as intended.

### 2. Tokens are scoped, and there are several

One token for everything is the current state and the thing to change. Per
ADR-018 §2 the JWT gains an **audience claim** listing the domains it is
valid for, and a **role** — `writer` (walks, the helper) or `reader` (a
dashboard, a friend's collection viewer). `setup_auth` mints them by name:

```
setup_auth --client-token --name ecky-thump --domains house,vehicles --role writer
setup_auth --client-token --name car-show-viewer --domains vehicles --role reader --expires 30d
```

The server records the token's name in every audit line and in `user_id`
on the versions it writes, so history says *which* client changed a thing.
Revocation is a server-side denylist of token ids (`jti`), checked on every
request; a leaked token is retired without rotating the secret.

### 3. The server secret stays where it is — with two changes

`JWT_SECRET` in a 700 start script under launchd is acceptable for a
single-operator host and is not worth a Keychain round-trip at process
start. Two changes: the secret is **never printed** (the upgrade script and
`add-domain.sh` currently echo the file they wrote it to; they stop), and
`setup_auth --rotate-secret` exists — it mints a new secret, rewrites every
domain's start script, restarts the services and re-mints every named token
into the Keychain, so rotation is one command rather than a procedure.

### 4. Third-party secrets follow the same rule

Home Assistant, UniFi, OVMS and MOT-history feed tokens are Keychain items
under the same service, account `<integration>@<host>`, read the same way.
The skills' README table of environment variables becomes a table of
Keychain accounts with the environment variables as the documented override.

## Consequences

- No credential in a file or a shell config on macOS once the clients are
  updated; backups and synced dotfiles stop carrying write access to the
  graph.
- Per-client tokens with audiences and roles let a friend read a vehicles
  graph without being able to write the house, and let the helper's grant be
  revoked on its own. History gains "which client", which the walks' audit
  notes want anyway.
- Linux (a headless server host, CI) keeps the file fallback; the Keychain
  path is macOS-only by nature, and the tests exercise the fallback.
- One more thing `setup_auth` must do well; it is already the place every
  credential decision lives, which is the point.

## Alternatives considered

- **1Password / a password-manager CLI** — works for a person, not for a
  daemon starting at login without a session; and it is a dependency on a
  product. The Keychain is what those tools use underneath.
- **Environment variables only, documented as sensitive** — the status quo;
  rejected above.
- **Short-lived tokens with refresh** — more moving parts than a denylist
  buys at this scale; revisit if a token is ever exposed in practice.
- **Move the server secret into the Keychain too** — the helper could hand
  it to the server over XPC at start, but that makes the server depend on
  the helper being installed and running first. Not worth the coupling.

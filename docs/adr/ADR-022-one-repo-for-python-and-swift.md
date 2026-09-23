# ADR-022: One repository for the engine and the Apple apps; an iOS 27 app rethought from scratch

**Status:** Accepted · 2026-09-23 · Owner decisions: *merge the Swift work
into one repo; archive the old Swift work; retain c11s-house-ios's deployment
setup and its HomeKit access code, none of its code or UI; the iOS app is
rethought from scratch.* The retained material is in `apple/`.

## Context

ADR-019 proposes a Swift macOS helper. The owner also wants a **Swift iOS 27
app** — the phone front end the walks are done from. Two Swift apps that
share most of their non-UI code (wire types, the tool client, auth and
Keychain, the session-file format, sync-degradation handling) and that must
stay on the same release as the server raise the question of where they
live.

Two Swift repositories already exist and neither is the answer:
`adrianco/c11s-house-ios` (a "conscious house" iOS app on a much older
protocol, last pushed 2026-01) and `adrianco/the-goodies-swift` (*WildThing*,
an untested client port, last pushed 2025-08). The TypeScript client
(`adrianco/the-goodies-typescript`) is a third, separately released repo,
and the cost of that separation has already shown: its CI checks out this
repo at a pinned ref, and twice a fix here needed a follow-up there.

## Decision

### 1. One repository: Python engine and Swift apps together

The Swift code lives in this repository under `apple/`, and nothing Swift
lives outside it:

```
apple/
  TheGoodiesKit/        Swift Package: the reference replica (store, sync, resolution, tool
                        executor -- ADR-023), wire types, Keychain, session-file (proposal)
                        format, the served domain manifest, HomeKit access
  EckyThump/            the macOS helper (Mac Catalyst) -- ADR-019
  Goodies/              the iOS 27 app
  Goodies.xcworkspace   both targets, the package by path
  deployment/           the retained deployment setup (entitlements, usage strings,
                        signing/build settings, release procedure)
  salvage/homekit/      the retained HomeKit code, reference only
```

**Why one repo.** The two apps share a package that is trivially a path
dependency in one repo and a tag-pinned dependency across two; the
same-release rule for both installs becomes one tag covering server, helper
and app; a protocol change lands with the conformance tests that pin it, in
one commit; and the ADRs, docs and issues are already here. The TypeScript
repo stays separate for now — its own package manager, CI and cadence gain
nothing from moving — and is reconsidered once the Kit exists and the drift
between the two clients can be measured.

**What it costs, and the arrangement for each:**

| Concern | Arrangement |
|---|---|
| CI | A second job on a macOS runner (`xcodebuild`: Kit tests, both targets), **path-filtered to `apple/`** so Python-only commits do not pay for macOS minutes. The Python job is unchanged. |
| Signing in CI | Build unsigned in CI; Developer ID / App Store signing and notarisation are a local release step (ADR-020: no secrets in files or CI). |
| Merge noise | `.gitattributes`: `*.pbxproj merge=union`; Xcode user state ignored. |
| Tooling | `ruff`/pytest already scope to Python; graphify indexes Swift too. |
| Weight | No binaries checked in; Xcode projects are text; assets stay small. |
| The Kit's contract | The same one every client has: `catalog_for(manifest)` and PROTOCOL.md. Its tests run the conformance cases against a FunkyGibbon started by the harness, exactly as KittenKong's do. |

### 2. The old repositories are archived; three things are retained

- `adrianco/c11s-house-ios` and `adrianco/the-goodies-swift` are **archived**
  on GitHub (read-only, history preserved).
- From c11s-house-ios, and only this, into `apple/`:
  1. **The deployment setup** — entitlements (`homekit`, `weatherkit`,
     sandbox, network client), the TCC usage-description strings, the
     signing and target build settings, the TestFlight/App Store procedure.
     The values that took effort to establish once.
  2. **The HomeKit access code** — `HomeKitService` / `Coordinator` /
     `Models` and their tests, as *reference* under `apple/salvage/`: the
     `HMHomeManager` authorization and delegate flow, and the walk from homes
     to characteristics into value types, are what `TheGoodiesKit` takes.
  3. Nothing else. No code, no UI.
- From the-goodies-swift: nothing.

### 3. The iOS 27 app is designed from scratch

The app is **not** a port of c11s-house-ios and not the WildThing client. It
is designed against what the walks have taught (ADR-016, #92, #99): the
phone is where a walk happens — camera, microphone, standing next to the
thing — and the app's job is to make a walk fast and to keep it honest
(session, review, confirm, read-back). Its design is a separate document
when the first vehicles walk has been done; this ADR only fixes where it
lives and what it inherits.

The tension first recorded here — helper not a replica (ADR-019 §4) versus
one replica (ADR-021) versus a phone in a garage with no signal — was
resolved the same day by ADR-023: every MCP client holds the graph, and
`TheGoodiesKit` is the Swift port of the reference replica (ADR-009),
embedded by both apps.

## Consequences

- A second language and toolchain in the repository (Swift, Xcode, signing),
  contained in `apple/` with its own CI job. The Python side is untouched.
- One tag per release for server, helper and app; `UPGRADE.md` gains an
  Apple section when there is something to upgrade.
- Two dead repositories stop being a question; the useful 5% of one is in
  `apple/` with its provenance written down.
- ADR-019 §5 (a separate `the-goodies-macos` repo) is superseded by this
  ADR; ADR-021 §1 gains the iOS app as the fourth client with one job.

## Alternatives considered

- **One repo per app** — rejected: the shared Kit becomes a tag-pinned
  dependency and every protocol change is a three-repo dance; the TypeScript
  repo already demonstrates the cost.
- **Everything, including KittenKong, in one repo** — deferred, not rejected;
  measure the drift first.
- **Port c11s-house-ios forward** — rejected by the owner: its protocol and
  UI predate everything in ADR-004 onward, and the walk-first model changes
  what the app is for.
- **Revive WildThing as the Kit** — rejected: untested, and written before
  the interval model, the manifest and the tool catalog existed.

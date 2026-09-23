# ADR-019: A signed macOS helper for the frameworks Python cannot reach

**Status:** Proposed · 2026-09-23 · Owner direction: *a Swift macOS helper that
deals with all the security-related things for HomeKit and other macOS
frameworks, running as a FunkyGibbon client daemon.* Nothing is built; this
records the shape it should have and the constraints that shape it.

## Context

The house domain's data comes from three kinds of source: what a person says
during a walk, what a network service will tell a script (Home Assistant's
REST API, a UniFi controller, a Vantage lighting probe), and what **Apple's
own frameworks** hold — HomeKit above all, but also Photos (every walk photo
is taken on an iPhone and lands in the library), Shortcuts (#95: Roland's
app-walk launches the app under walk from a Shortcuts library), Bluetooth and
the local network (device discovery), and Location (a vehicle's "where was
it" from the phone).

Today the Apple side is reached by a hack that the skills themselves flag as
such: *"a script reading `~/Library/HomeKit/core.sqlite`, which needs Full
Disk Access"* (`align-rooms`, `room-walk`). That is a reverse-engineered,
undocumented database read with the broadest privacy grant macOS offers,
by an unsigned Python process. It works until Apple changes the schema, it
cannot write anything back, it cannot receive events (a light turned on, a
new accessory paired), and granting Full Disk Access to `python3` is the
opposite of the least-privilege story the rest of the system tells.

Two constraints decide the architecture and are easy to get wrong:

1. **HomeKit is not available to AppKit processes.** `HMHomeManager` is
   iOS/iPadOS/tvOS/watchOS and, on the Mac, **Mac Catalyst only**. A Swift
   command-line tool or a plain AppKit daemon cannot link it. Either the
   helper is a Catalyst app, or it reads the sqlite file like the script does.
2. **Every one of these frameworks is gated by TCC** (Transparency, Consent,
   Control): the process must be a **signed, notarised app bundle** with
   usage-description strings in its `Info.plist`, and the user must click
   through a prompt per capability. Consent is recorded against the bundle
   identifier. A daemon that is not an app bundle gets no prompt and no
   access; a bundle whose signature changes loses the consent it had.

Neither constraint is negotiable, and both are foreign to a Python project.
That is the reason for a separate, Swift, Apple-native component rather than
another script.

## Decision

### 1. One helper app, Swift, Mac Catalyst, a FunkyGibbon *client*

A single signed and notarised **Mac Catalyst** application, provisionally
`Ecky-Thump` (the Goodies' Lancashire martial art: it deals with the
dangerous things so nothing else has to; the owner may rename it). It runs as
a **login item registered with `SMAppService`** — the modern launchd agent
for an app, which survives reboots, shows in System Settings › Login Items,
and can be enabled and disabled by the user without a plist — and it keeps
no window open by default; a menu-bar item shows status and hosts the
consent flows.

It is a **client of FunkyGibbon**, exactly like KittenKong or blowing-off:
it authenticates with a client token, talks to a domain's endpoint over
`/api/v1/mcp/tools/*`, and never opens a database file. It writes through
the tools, so every write is validated against the domain's manifest,
versioned, and visible to sync. It is not a server, holds no replica in the
first version (§4), and is not on the sync protocol.

### 2. It owns every Apple-framework capability, and nothing else does

| Capability | Framework | What the helper does with it |
|---|---|---|
| HomeKit | `HomeKit` (Catalyst) | Read homes, rooms, accessories, services, characteristics; **subscribe** to changes (`HMHomeManagerDelegate`, characteristic notifications); optionally write (rename a room per `align-rooms`, set a scene). Replaces the `core.sqlite` read outright. |
| Photos | `PhotoKit` | Fetch walk photos by date/album so a walk can attach them without the user exporting files; write nothing. |
| Shortcuts | `AppIntents` | Expose "Start a room walk", "Open app X for walk", "Record a fuel stop" as intents, so the phone's Shortcuts app and Siri can drive the graph (#95's launch step becomes native). |
| Local network | `Network` / Bonjour, `NWBrowser` | Discover devices advertising on the LAN (HomeKit accessories, printers, TVs) for the room walk's "what's here" step, replacing the UniFi-only heuristic where no controller exists. |
| Bluetooth | `CoreBluetooth` | Nearby-device hints during a walk (an e-bike, an OBD dongle). |
| Location | `CoreLocation` | The vehicles domain's `where` on a fuel stop or a sighting, from the Mac's or the phone's location via Continuity. |
| Speech | `Speech` (on-device `SFSpeechRecognizer`) | Transcribe a walk on the Mac without sending audio anywhere: the transcript `note` that every walk writes, produced locally. |
| On-device LLM | `FoundationModels` (Apple Intelligence; macOS 26, and whatever macOS 27 adds — owner note 2026-09-23) | The parts of a walk that are language, not judgement, run locally and free: turn a transcript into proposed diffs, summarise a vehicle's history for a show entry, name an `event.kind` from what was said, draft the review. Guided generation (`@Generable`) gives typed output that maps onto the session-file diffs directly. The frontier model stays for the conversation itself and anything that needs the whole graph; the helper's model is for the always-on, private, no-network passes. |
| Notifications | `UserNotifications` | "Sync has been failing for 2 days", "the vehicles walk session is still open" — the `sync.degraded` flag with somewhere to go. |
| Keychain | `Security` | Holds the client token and any secrets the helper needs (ADR-020). |

Each capability is **requested lazily, on first use, with its usage string
explaining what the graph will do with it**, and each is independently
revocable in System Settings. The on-device model is the one capability with
no consent prompt and no network, which is why it is the right place for
transcript-to-diff and summarisation: the raw walk audio and the whole
history of a car need never leave the machine to become structured. It is
also the one most likely to change shape between macOS releases; the helper
treats it as optional and falls back to sending text to the frontier model
the skill is already talking to. The helper degrades per capability: no Photos
consent means walks attach files by hand, as today; nothing else changes.

### 3. Sources produce proposals, not writes

The helper is a *source*, and sources feed the walk (ADR-016 §1.1, the
room-walk's "local until saved"). A HomeKit reconciliation does not write
rooms into the graph; it produces a **review** — the same session/diff/confirm
mechanism the skills use — of what HomeKit knows that the graph does not, and
vice versa. The user confirms; then the helper commits through the tools.
The one exception is **events from a subscription** at logbook granularity
(an accessory was added, a room was renamed in the Home app): those are
written as `event`s / `note`s with `source_type: imported` straight away,
because they are facts about what happened, not proposals about what is.

The proposal format is the skills' session file (`room_session.py`'s JSON):
the helper writes one, the skill reviews it. That keeps the human-in-the-loop
mechanism in one place and lets the helper be replaced without touching the
skills.

### 3a. Where the two models sit

```
walk conversation ──▶ frontier model (Claude, via the skill)   judgement, the whole graph, the user
      │
      ├─ audio ───────▶ helper: Speech → transcript (local)
      └─ transcript ──▶ helper: FoundationModels → proposed diffs, summaries (local, typed)
                              └─▶ session file ──▶ review ──▶ confirm ──▶ tools
```

The helper never talks to the frontier model; the skill does. The helper's
outputs are proposals in the session file like any other source's (§3), so a
wrong local extraction is caught at review, not in the graph.

### 4. What it is not, in the first version

- **Not a replica.** No local store, no sync loop; it reads and writes over
  HTTP when the server is reachable and queues nothing. Offline capture stays
  with KittenKong and the phone. If a Swift replica is ever wanted, it is a
  port of the reference client per ADR-009 and a separate decision.
- **Not the iOS app.** `c11s-house-ios` is the phone front end; this is the
  Mac's system-integration daemon. They may share Swift packages (the
  inbetweenies wire types, the tool client) but not a target.
- **Not a server-side component.** It never touches `funkygibbon.db`, the
  JWT secret, or launchd entries for the server.

### 5. Packaging and trust

- Xcode project in its own repository (`adrianco/the-goodies-macos`,
  proposed), Catalyst target, hardened runtime, notarised, distributed as a
  signed `.app` (no App Store: it needs no entitlements the store forbids,
  but the review cycle would slow every fix). Developer ID signing is the
  cost of TCC; there is no unsigned path.
- Configuration is the server URL(s) per domain and nothing else; the token
  comes from the Keychain (ADR-020), minted once by `setup_auth` on the
  server host.
- The helper reports its own state as a FunkyGibbon `app` entity that
  `manages` what it reads (base vocabulary, ADR-013 §4): which capabilities
  are granted, when it last reconciled. `get_connected` on the home then
  says how the graph is being fed.

## Consequences

- HomeKit becomes a first-class, supported, *live* source with a documented
  API instead of a reverse-engineered database; Full Disk Access is no longer
  requested by anything. The `align-rooms` and `room-walk` "HomeKit export"
  steps are replaced by the helper's proposal.
- A new language and toolchain in the project, unavoidable: Swift, Xcode,
  code signing. Contained in one repository with one job.
- Every capability grant is explicit, per-purpose and revocable, which is a
  better security story than one Python process with Full Disk Access — and
  a worse one than nothing at all: the helper is a signed process with access
  to the home's accessories, and its token is a write credential. ADR-020
  makes the credential handling match.
- The walk skills gain a source that can answer "what is actually in this
  room right now" from the Home app, and "what changed since the last walk"
  from subscriptions, which is the difference between cataloguing and keeping
  a catalogue current.

## Alternatives considered

- **Keep reading `core.sqlite`** — rejected: undocumented schema, read-only,
  no events, Full Disk Access for an interpreter, and it is the thing the
  skills already apologise for.
- **A Swift command-line daemon (no app bundle)** — rejected: cannot link
  HomeKit (Catalyst only) and gets no TCC consent for anything else.
- **Home Assistant as the HomeKit bridge** (its HomeKit Controller
  integration) — viable where HA runs (Corfe), absent where it does not
  (Roland runs Vantage), and it still leaves Photos, Shortcuts, Bluetooth and
  Location unreachable. Kept as a *source* alongside the helper, not instead.
- **Put the capabilities in the iOS app** — the phone has HomeKit too, but
  it is not always on, not on the LAN, and not a daemon; a Mac at home is.
- **Make the helper a full sync replica** — deferred (§4): it doubles the
  surface for no first-version benefit; the Mac is on the LAN with the server.

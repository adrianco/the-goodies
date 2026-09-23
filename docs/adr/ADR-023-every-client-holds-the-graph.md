# ADR-023: Every MCP client holds the knowledge graph; filtering is optional; domains are data to a client

**Status:** Accepted · 2026-09-23 · Owner decisions: *an iOS app, a macOS
app and a shared library; every MCP client caches the full knowledge graph,
with optional filtering; the apps support all domains in an extensible way.*
Supersedes ADR-019 §4 (the helper as a thin, replica-less client) and the
"one replica" rule of ADR-021 §1; resolves the tension ADR-022 §3 recorded.

## Context

The previous three ADRs tried to keep the number of replicas at one
(KittenKong) and make the Swift helper a thin HTTP tool client. The owner's
direction is the opposite and simpler: **an MCP client is a replica.** Every
one of them — KittenKong, the iOS app, the macOS helper — holds the graph
locally, serves its tools from that copy, and syncs. That is what makes a
walk work in a garage with no signal, makes `search_entities` fast, and
makes a client's answers independent of the server being up; it is also the
design ADR-009 already specified as *the reference client*, of which
KittenKong is one port and the Swift Kit is the next.

Two refinements come with it. **Filtering is optional**: a client may hold a
subset — exclude older data, focus on or exclude particular vehicles, hold
one domain — and must say so, so that a filtered answer is never mistaken
for a complete one. And **the
apps support every domain without domain code**: a Swift app must render the
vehicles graph and the house graph, and a third domain that does not exist
yet, from what the server tells it about the domain.

## Decision

### 1. `TheGoodiesKit` is the reference client in Swift, and both apps embed it

The shared library (`apple/TheGoodiesKit/`, ADR-022) is a port of the
reference client design (ADR-009): one SQLite store per domain replica with
the server's table shapes (immutable entity versions, interval edges, the
`is_latest` / `server_seq` columns), the inbetweenies-v3 sync engine with
per-id acks, the pull-guard and the resolution rule, the pending-mark
transaction rules, and the tool executor that runs the engine's 18 tools and
any domain's declared walks (`DomainTool` / `Walk`) against the local store —
the same executor blowing-off and KittenKong have. The conformance suite
(ADR-010) runs against it as it does against them.

The iOS app and the macOS helper are two UIs and two sets of platform
capabilities over the same Kit. The helper is therefore a replica too;
ADR-019 §2's Apple-framework capabilities are unchanged, and ADR-019 §3's
rule still holds — sources propose, walks commit — with the proposal now
reviewed and committed against the local replica and synced, exactly as a
KittenKong walk is.

### 2. A client holds one replica per domain it is configured for

Domains are separate back ends (ADR-018); a client holds one store and one
sync loop per domain endpoint it is pointed at, each with its own cursor and
digest, and exposes one merged MCP surface whose tool names are prefixed
only where two domains collide (they do not today: the engine's 18 are
shared and domain tools are distinct by name). Adding a domain to a client is
adding an endpoint; there is no per-domain client code (§4).

### 3. Filtering is a declared subset, never a silent one

Owner clarification (2026-09-23): filtering is for **excluding older data**
and for **focusing on, or excluding, specific vehicles** — not for reshaping
the vocabulary. So the filters a replica may declare are:

| Filter | What it means | Mechanism |
|---|---|---|
| **Horizon** — exclude older data | Hold history from an instant onward; earlier versions and ended intervals are not fetched | ADR-009 §5: sync from a cursor floor / `SyncFilters.since`; as-of reads before the horizon are refused offline or proxied when online, never answered wrongly |
| **Focus** — only these things | Hold the subgraph *about* a set of anchor entities: the vehicles named, plus everything that reaches them — their events, parts and their intervals, locations, tools, documents and photos | new `SyncFilters.focus: [entity ids]`; the **server** computes the closure per pull (a walk over the domain's relationship rules from the anchors, both directions, to a bounded depth) so the client never needs the whole graph to know what belongs |
| **Exclude** — everything but these | The complement: hold the graph minus the subgraph about the named anchors | `SyncFilters.exclude: [entity ids]`, same closure, subtracted |
| By domain | Which endpoints the client is configured for | ADR-018; a friend's phone holds vehicles and not the house |

Focus and exclude take **entity ids**, and the manifest says which types are
sensible anchors (`vehicle`, `home`); the Kit offers them by name from the
served manifest (§4). A vehicle sold years ago, a friend's car you help with,
a race car whose spares pile is half the graph — each is one anchor in one
list. The existing `SyncFilters.entity_types` stays for the cases that want
it but is not the tool for this.

The default is **everything**, and a filtered replica's tool results carry
the filter in the response — `replica: {domains, since, focus, exclude}` —
the same way `sync.degraded` travels (typescript#4): a caller can always
tell a partial answer from a complete one, and a walk on a focused replica
knows it cannot see the car it excluded. Changing a filter is a re-sync of
the affected subgraph, not a wipe. Blob bytes remain lazy everywhere
(ADR-007's surviving fields): a replica holds every blob *row* in its subset
and fetches `data` on demand through `get_blob`.

### 4. A domain is data to a client: the server publishes its manifest

For an app to support every domain without domain code, the domain's
description must be readable over the wire. The engine gains one endpoint,
`GET /api/v1/domain`, returning the served manifest as JSON — name, entity
types with the attachment flag, relationship rules with their endpoint
pairs, source types, the declared tools (already in the catalog) and the
skills' names — and the same document is written into the replica's
metadata at first sync so it is available offline.

A client uses it for everything that would otherwise be a `switch` on the
domain: which types it may create, which edges are legal between two things
it is showing, how to label and group entities, which walks to offer, what
the vocabulary's words are. The manifest may carry optional **presentation
hints** for this purpose — an icon name and a display label per type, an
ordering, which content keys are the "headline" fields (`make`/`model`/`year`
for a vehicle, nothing for a note) — declared by the domain author alongside
the vocabulary and ignored by the engine. A domain that declares none gets a
generic rendering, which must be adequate: the third domain is the test.

Domain-specific *behaviour* in a client (a race-car walk's prompt pack, an
odometer-unit toggle) is a **plugin keyed by manifest name**, loaded if
present and absent without consequence. The engine's isolation rule applies
to the Kit as to `inbetweenies`: nothing in the Kit imports a domain.

### 5. What this changes in the earlier ADRs

- ADR-019 §4 "not a replica" — **superseded**; the helper embeds the Kit.
- ADR-021 §1 "one replica" — **superseded**: a replica per MCP client, one
  reference design, ports in TypeScript and Swift. The rest of ADR-021 (one
  Python tool client in `oook`, the source contract, skills as prompt packs,
  `oook doctor`) stands.
- ADR-022 §3's recorded tension — **resolved** in favour of the replica.
- ADR-018 §3 (KittenKong reads its domain's catalog) — **extended**: every
  client reads the manifest, not only the catalog.

## Consequences

- The Kit is the largest piece of Swift to write and the one that matters
  most: store, sync, resolution, tool executor. It is a port of a design with
  a conformance suite, two existing implementations to read, and PROTOCOL.md
  written to be implemented from — not a design.
- The engine gains `GET /api/v1/domain` and the optional presentation hints
  in `DomainManifest`; KittenKong gains the same manifest-driven behaviour
  (it currently hard-codes the house). Both are small.
- A filtered replica is a first-class, declared thing, so the friend's
  vehicles-only phone, a replica that stops at last year, one that holds
  only the race car, and the full house replica are the same code.
- The engine gains the server-side subgraph closure for `focus` / `exclude`
  (a walk over the manifest's relationship rules from the anchors), which
  is the one non-trivial addition; it is also exactly what ADR-017's
  reverse lookup and `oook`'s "export one vehicle" want.
- Three replicas to keep conformant instead of one; the suite is the
  mechanism, and it already runs against two.

## Alternatives considered

- **Thin clients over HTTP, one replica** (ADR-019/021 as first written) —
  rejected by the owner: offline walks, speed and independence from the
  server matter more than the count of replicas.
- **Domain code per app** (a house module, a vehicles module) — rejected: it
  is the pre-ADR-012 mistake at the client, and the third domain would need
  an app release. The manifest is the data; plugins are for behaviour only.
- **Filtering as a client-side afterthought** (hold everything, hide some) —
  rejected for the friend's-phone case: not holding the house is a privacy
  property, not a display one.

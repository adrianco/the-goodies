# The house domain

The complete vocabulary of the smart-home knowledge graph: what the engine will
accept, what has actually been created, and where the two diverge.

Adding a domain means writing one of these. Nothing in `funkygibbon`,
`inbetweenies` or `blowing-off` may import it — see [No domain leakage](#no-domain-leakage).

> **Usage counts are from the live instance** — 423 entities (510 version
> rows), 461 relationships, taken from the 2026-08-03 production backup **after
> the ADR-013 migration**. Counts are of *current* rows only; history would
> double-count edits.
>
> An earlier version of this document used the development database and drew
> largely wrong conclusions from it. That database is `populate_graph_db.py`
> seed data — a demo of the whole model — so it exercised nearly every type and
> made the vocabulary look well used. The real house uses about half of it, and
> uses different parts. Where the two disagree, this table is right.

---

## Entity types — 13 available, 7 in use

Two of these come from the **base** vocabulary and are not declared here:
`photo` and `app`. Blobs and external systems are engine mechanism, so every
domain inherits them — see [Base vs domain](#base-vs-domain).

| Type | Live | Notes |
|---|---:|---|
| `device` | 289 | 68% of everything. |
| `room` | 50 | |
| `door` | 29 | |
| `photo` | 27 | **Base.** Every blob in the database. Created by ADR-013 §3 from notes that were wrapping images. |
| `note` | 26 | Now only genuine text notes — walk/edit session records. |
| `home` | 1 | |
| `app` | 1 | **Base.** One `Alexa` entity. `manages` is still 0 — see below. |
| `zone` | 0 | **Unused.** Declared as the layer between room and home; the real house is flat. `located_in` has zone rules that nothing exercises. |
| `manual` | 0 | **Unused.** The house's *own* attachment type — a PDF (ADR-013 §3). Nothing has attached a PDF yet; `documented_by` is used 16× but always onto `note`. |
| `automation` | 0 | **Undescribed** — see below. |
| `schedule` | 0 | **Undescribed.** |
| `procedure` | 0 | **Undescribed.** |
| `window` | 0 | **Unused**, while `door` has 29. |

**The automation vocabulary is undescribed, not unbuilt.** `automation`,
`schedule` and `procedure` have no instances, and the relationship types serving
them are also at zero. That is not a feature that was modelled and abandoned:
the Vantage system at one site and Home Assistant at the other physically exist
and simply have not been entered into the graph. The vocabulary is waiting for
them, which is why ADR-013 kept it.

## Relationship types — 12 available, 5 in use

| Type | Live | Allowed endpoints | Notes |
|---|---:|---|---|
| `located_in` | 300 | device→room, device→zone, room→zone, room→home, zone→home, door→room, window→room | The containment spine. Gained 48 edges from `part_of` in the ADR-013 split. |
| `part_of` | 104 | device→device | Composition only, since the split. |
| `has_photo` | 26 | *→photo | **Base.** Replaces `has_blob` (ADR-013 §3). The wildcard is deliberate: the engine cannot enumerate a domain's types. |
| `documented_by` | 16 | device→manual, device→procedure, device→note, room→note, home→note, door→note | Attaches to `note` in practice; `manual` and `procedure` have no instances. |
| `connects_to` | 15 | room→room, door→room, window→room | The 29 doors. |
| `controls` | 0 | device→device, automation→device, … | Awaiting the automation description. |
| `automates` | 0 | automation→device, schedule→device | Awaiting. |
| `triggered_by` | 0 | automation→device, schedule→automation | Awaiting. |
| `procedure_for` | 0 | procedure→device, procedure→room | Awaiting. |
| `monitors` | 0 | device→device, device→room, automation→device | Awaiting. |
| `manages` | 0 | app→device, app→automation, app→schedule, app→room | **Base, narrowed here.** Base says `app→*`; the house restricts it to these four. How an automation records which system runs it (ADR-013 §4). The `Alexa` app exists; nothing links to it yet. |
| `depends_on` | 0 | *(unconstrained)* | Was uncreatable — declared no endpoints, so every attempt failed. Now explicitly unconstrained (ADR-013 §2). |

**Every live edge conforms to these rules** — verified against the migrated
production copy. Before ADR-013 there were 107 violations, because the endpoint
check ran on one write path of three.

### Deleted by ADR-013

| Was | Why |
|---|---|
| `contained_in` | Duplicated `located_in`, declared no endpoints, never creatable. |
| `controlled_by_app` | The exact inverse of `manages`. Both unused, so there was no cost to choosing one; the app is the actor, so it reads as the subject. |
| `has_blob` | Never pointed at a blob — it pointed at a note that carried one. Replaced by `has_photo`. See below. |

## How blobs are linked

**One rule: an entity that carries a blob is an attachment entity, and top-level
`content.blob_id` is the only link to the `blobs` table.**

The entity type says what kind of document it is, so no boolean "this has a
blob" flag is needed — the type *is* the flag. Relationships never point at a
blob; they only say what role the attachment plays.

```
device --has_photo--> photo --content.blob_id--> blobs   (images, base)
device --documented_by--> manual --content.blob_id--> blobs   (PDFs, house)
```

Adding a further kind — video, wiring diagram — is a new entity type, not new
plumbing. Declare it in `attachment_types` and `manifest.carries_blob()` knows
about it.

**`photo` and `has_photo` are base, not house.** Blobs are engine machinery, so
the vocabulary for reaching one lives in `inbetweenies/domain.py` and every
domain inherits it. The house contributes only `manual`, because an appliance
PDF is house-flavoured where an image is universal.

This replaced **six** accumulated conventions (a `has_blob` edge, top-level
`blob_id`, nested `images[].blob_id`, a `screenshot_blob_ids` array, and two
differently-named boolean flags meaning the same thing). ADR-013 §3 has the full
inventory and the migration.

Current state: 27 blobs, 27 `photo` entities, no dangling references and no
orphaned blobs. 26 of the 27 photos are linked by a `has_photo` edge; one has
never been attached to anything.

**One documented exception:** photos nested under `content.images[]` on the
owning entity are normalised to blob references by `migrate.py::_extract_photos`
rather than split into `photo` entities. Zero rows in either live install use
this shape; it survives as an import-time form.

## Source types — 5 declared, 4 in use

| Type | Live | Notes |
|---|---:|---|
| `imported` | 265 | The bulk of the graph. |
| `homekit` | 72 | |
| `manual` | 69 | Human-entered. |
| `generated` | 17 | |
| `matter` | 0 | **Unused.** The only unused source type. |

The provenance feature *is* exercised — four of five in real use, with a
meaningful spread. (An earlier draft of this document called it "entirely
unexercised" on the strength of seed data, where everything is `generated`.)

`source_type` answers *how did this record reach the graph*, and deliberately
nothing more. Which system *runs* an automation is a separate fact that stays
true however the record arrived, and belongs on an `app` entity — see ADR-013 §4
for why extending this list per vendor does not scale.

---

## What this suggests

Everything from the previous edition of this list has been decided in ADR-013:
the `located_in`/`part_of` conflation is split, `contained_in` and
`controlled_by_app` are deleted, `depends_on` is usable, the automation
vocabulary is retained as undescribed-not-absent, and blob linking has converged
on one mechanism.

**Still open:**

1. **Enforcement on every write path** (ADR-013 §5). The endpoint rules run on
   the MCP path only; REST has the check commented out and sync never checks.
   The data now conforms, so enabling it is safe — that ordering was the point.
2. **`window` and `matter`** — declared, no instances, rules exist for both.
3. **`manual` has no instances** while `documented_by` is used 16×, always onto
   `note`. Either PDFs have not been added yet, or documentation genuinely is
   all free text.

**Overall: 7 of 13 entity types (2 of them base), 5 of 12 relationship types
and 4 of 5 source types are in use.** A little over half the vocabulary is load-bearing. That is
not itself a problem — vocabularies are meant to outrun their data — but it is
worth knowing which half before a second domain is modelled on this one.

---

## Base vs domain

| | Declared in | Why |
|---|---|---|
| `photo`, `has_photo` | base (`inbetweenies/domain.py`) | Blobs are engine machinery; every domain has photos. |
| `app`, `manages` | base | An external system acting on entities is not a house concept. |
| `manual` | house, via `attachment_types` | An appliance PDF is house-flavoured; the base knows only that it carries a blob. |
| everything else | house | Genuinely about buildings. |

A domain may **narrow** a base relationship rule by redeclaring it under the
same name — the house does this to `manages`. It may not widen one; that would
make the base rule decorative.

Because the base cannot enumerate a domain's entity types, base rules use the
wildcard `"*"` in one endpoint position. `tests/test_domain_manifest.py` pins
all of this, including that the house does *not* re-declare base vocabulary —
checked against the source, since the assembled manifest contains `photo` either
way and could not tell the difference.

## No domain leakage

The engine must not know about any specific domain. That is enforced, not
assumed: `tests/test_domain_isolation.py` asserts that no module under
`funkygibbon/`, `inbetweenies/` or `blowing-off/` imports `domains.*`.

A second domain is the real proof. If `domains/vehicles` can be added with no
engine change, the abstraction is real; if the engine needs a line, it is not.

## Declared, not derived

The house vocabulary was originally *derived* from the `EntityType`,
`SourceType` and `RelationshipType` definitions it replaces, and from the
predicate that owned the endpoint rules — verified equal across all 2016
`(relationship_type, from_type, to_type)` triples. That proved ADR-012 changed
only *where* the rules lived.

ADR-013 changes what they *say*, so deriving them is no longer possible. This
manifest is now the source of truth and the enums it came from are legacy. A new
domain declares its vocabulary directly, having nothing to derive from.

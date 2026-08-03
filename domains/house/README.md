# The house domain

The complete vocabulary of the smart-home knowledge graph: what the engine will
accept, what has actually been created, and where the two diverge.

Adding a domain means writing one of these. Nothing in `funkygibbon`,
`inbetweenies` or `blowing-off` may import it — see [No domain leakage](#no-domain-leakage).

> **Usage counts are from the live instance** — 423 entities (510 version
> rows), 461 relationships, taken from the 2026-08-03 production backup. Counts
> are of *current* rows only; history would double-count edits.
>
> An earlier version of this document used the development database and drew
> largely wrong conclusions from it. That database is `populate_graph_db.py`
> seed data — a demo of the whole model — so it exercised nearly every type and
> made the vocabulary look well used. The real house uses less than half of it,
> and uses different parts. Where the two disagree, this table is right.

---

## Entity types — 12 declared, 6 in use

| Type | Live | Notes |
|---|---:|---|
| `device` | 289 | 68% of everything. |
| `note` | 53 | |
| `room` | 50 | |
| `door` | 29 | |
| `home` | 1 | |
| `app` | 1 | Used, but see `controlled_by_app` and `manages` below — both 0. |
| `zone` | 0 | **Unused.** Declared as the layer between room and home; the real house is flat. `located_in` and `part_of` both have zone rules that nothing exercises. |
| `automation` | 0 | **Unused.** |
| `schedule` | 0 | **Unused.** |
| `procedure` | 0 | **Unused.** |
| `manual` | 0 | **Unused**, though `documented_by` is used 16× — so documentation attaches to `note`, not `manual`. |
| `window` | 0 | **Unused**, while `door` has 29. |

**The automation half of the model does not exist in practice.** `automation`,
`schedule` and `procedure` have no instances, and every relationship type that
connects them — `automates`, `controls`, `triggered_by`, `procedure_for`,
`monitors`, `manages` — is also at zero. That is six of fourteen relationship
types and three of twelve entity types forming one unused subsystem, not
scattered gaps.

## Relationship types — 14 declared, 5 in use

| Type | Live | Allowed endpoints | Notes |
|---|---:|---|---|
| `located_in` | 252 | device→room, device→zone, room→zone, room→home, zone→home | The containment spine. |
| `part_of` | 152 | room→home, zone→home, device→zone | Overlaps `located_in` — see below. |
| `has_blob` | 26 | *(unconstrained)* | **In active use.** Blobs are linked by relationship *and* by `content.blob_id` (see `migrate.py::_extract_photos`) — two mechanisms, both live. |
| `documented_by` | 16 | device→manual, device→procedure, device→note, … | Attaches to `note`; `manual` and `procedure` have no instances. |
| `connects_to` | 15 | room→room, door→room, window→room | The 29 doors. |
| `controls` | 0 | device→device, automation→device, … | Unused — no automations exist. |
| `automates` | 0 | automation→device, schedule→device | Unused. |
| `triggered_by` | 0 | automation→device, schedule→automation | Unused. |
| `procedure_for` | 0 | procedure→device | Unused. |
| `monitors` | 0 | device→device, device→room | Unused. |
| `manages` | 0 | app→device, app→automation | Unused, despite one `app` entity existing. |
| `controlled_by_app` | 0 | device→app | Unused — the app is present but connected to nothing. |
| `contained_in` | 0 | **none** | **Unusable.** See below. |
| `depends_on` | 0 | **none** | **Unusable.** See below. |

### `contained_in` and `depends_on` cannot be created

Both declare *no* permitted endpoint pairs, and `create_relationship` rejects
any edge whose pair is not permitted (`inbetweenies/mcp/tools.py:243`). Every
attempt fails, for every combination of entity types. This is a code fact and
holds regardless of the data.

Invisible while the rules lived as a dict literal inside a method; obvious now
the vocabulary is data. The manifest reproduces it exactly rather than quietly
granting them endpoints, because the abstraction's premise is that behaviour
does not change — fixing it is a deliberate edit to the house vocabulary.

**Decide:** give them endpoints, mark them explicitly unconstrained
(`allowed_endpoints=None`), or delete them.

### Two hierarchies doing one job — 404 edges between them

`located_in` (252) and `part_of` (152) both express containment and share the
pairs room→home, zone→home, device→zone. Together they are 88% of all
relationships. A traversal asking "what is in this room" gets a different answer
depending on which it follows, and nothing declares which is canonical.

`inbetweenies/graph/traversal.py` treats both as child→parent for ancestry, so
they are already interchangeable to the engine. This is the most consequential
open question in the vocabulary.

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

---

## What this suggests

**Should decide, in rough order of consequence:**

1. **`located_in` vs `part_of`** — 404 edges, 88% of the graph, no declared
   canonical. Collapse to one, or document the distinction.
2. **The automation subsystem** — `automation`, `schedule`, `procedure` and the
   six relationship types serving them are entirely unused. Either the house
   has not reached that feature yet, or the model anticipated something that did
   not happen. Half the relationship vocabulary rests on the answer.
3. **`contained_in` / `depends_on`** — unusable as declared.
4. **`app`** — one entity, connected by nothing. `manages` and
   `controlled_by_app` are both zero.
5. **Two blob-linking mechanisms** — `has_blob` (26) and `content.blob_id` are
   both live. Pick one.
6. **`window` and `matter`** — declared, no instances, rules exist for both.

**Overall: 6 of 12 entity types, 5 of 14 relationship types and 4 of 5 source
types are in use.** A little over half the vocabulary is load-bearing. That is
not itself a problem — vocabularies are meant to outrun their data — but it is
worth knowing which half before a second domain is modelled on this one.

---

## No domain leakage

The engine must not know about any specific domain. That is enforced, not
assumed: `tests/test_domain_isolation.py` asserts that no module under
`funkygibbon/`, `inbetweenies/` or `blowing-off/` imports `domains.*`.

A second domain is the real proof. If `domains/garage` can be added with no
engine change, the abstraction is real; if the engine needs a line, it is not.

## Deriving, not transcribing

The house vocabulary is currently *derived* from the `EntityType`,
`SourceType` and `RelationshipType` definitions it replaces, and from the
predicate that owned the endpoint rules — verified equal across all 2016
`(relationship_type, from_type, to_type)` triples.

That is deliberate for the migration step: retyping 31 names and ~40 endpoint
pairs by hand would put "byte-identical" at the mercy of a typo. A new domain
declares its vocabulary directly, having nothing to derive from.

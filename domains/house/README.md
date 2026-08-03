# The house domain

The complete vocabulary of the smart-home knowledge graph: what the engine will
accept, what has actually been created, and where the two diverge.

Adding a domain means writing one of these. Nothing in `funkygibbon`,
`inbetweenies` or `blowing-off` may import it — see [No domain leakage](#no-domain-leakage).

> **Usage counts** are from the development database (25 entities, 35
> relationships). The live instance is roughly 17× larger (423 entities, 461
> relationships per the 2026-08 design review) and its *distribution* has not
> been measured — a type showing 0 here could be in use there. Treat the zeros
> as "worth checking", not as proof. Every "unusable" claim below is about the
> code, not the data, and holds regardless.

---

## Entity types — 12 declared, 10 in use

| Type | Used | Notes |
|---|---:|---|
| `home` | 1 | Root of the containment hierarchy. |
| `room` | 6 | |
| `zone` | 3 | Groups rooms; sits between room and home. |
| `device` | 6 | |
| `door` | 1 | |
| `window` | 0 | **Gap.** Declared alongside `door`, which is used. Either the model wants windows and nothing creates them, or it is aspirational. |
| `procedure` | 2 | |
| `manual` | 1 | |
| `note` | 2 | |
| `schedule` | 1 | |
| `automation` | 2 | |
| `app` | 0 | **Unused feature.** Added for "HomeKit, Comfort app, etc." Its partner relationship `controlled_by_app` is also unused, so the whole app-attribution feature is declared and never exercised. |

## Relationship types — 14 declared, 9 in use

| Type | Used | Allowed endpoints | Notes |
|---|---:|---|---|
| `located_in` | 11 | device→room, device→zone, room→zone, room→home, zone→home | The containment spine. |
| `part_of` | 9 | room→home, zone→home, device→zone | Overlaps `located_in` — see [Two hierarchies](#two-hierarchies-doing-one-job). |
| `connects_to` | 3 | room→room, door→room, window→room | The only place `window` appears in a rule. |
| `documented_by` | 3 | device→manual, device→procedure, device→note, … | |
| `controls` | 2 | device→device, automation→device, schedule→device, schedule→automation | |
| `automates` | 2 | automation→device, schedule→device | Overlaps `controls`. |
| `manages` | 2 | app→device, app→automation | Uses `app`, which has no instances. |
| `procedure_for` | 2 | procedure→device | |
| `monitors` | 1 | device→device, device→room | |
| `has_blob` | 0 | *(unconstrained)* | **Dead in practice.** Blobs are referenced by `content.blob_id` instead — see `funkygibbon/migrate.py::_extract_photos`. Two mechanisms, one used. |
| `triggered_by` | 0 | automation→device, schedule→automation | |
| `controlled_by_app` | 0 | device→app | Half of the unused app feature. |
| `contained_in` | 0 | **none** | **Unusable.** See below. |
| `depends_on` | 0 | **none** | **Unusable.** See below. |

### `contained_in` and `depends_on` cannot be created

Both declare *no* permitted endpoint pairs, and `create_relationship` rejects
any edge whose pair is not permitted (`inbetweenies/mcp/tools.py:243`). So every
attempt to create one fails, for every combination of entity types.

This was invisible while the rules lived as a dict literal inside a method; it
is obvious now that the vocabulary is data. The manifest reproduces it exactly
rather than quietly granting them endpoints, because the abstraction's premise
is that behaviour does not change — fixing it is a deliberate edit to the house
vocabulary, not a side effect of moving it.

**Decide:** give them endpoints, mark them explicitly unconstrained
(`allowed_endpoints=None`), or delete them.

### Two hierarchies doing one job

`located_in` and `part_of` both express containment and share the pairs
room→home, zone→home, device→zone. Both are in active use (11 and 9). A
traversal asking "what is in this room" gets a different answer depending on
which it follows, and nothing declares which is canonical.

`inbetweenies/graph/traversal.py` treats both as child→parent for ancestry, so
they are already interchangeable to the engine. Worth collapsing to one, or
documenting the distinction if there is one.

## Source types — 5 declared, 1 in use

| Type | Used | Notes |
|---|---:|---|
| `generated` | 25 | Everything. |
| `homekit` | 0 | |
| `matter` | 0 | |
| `manual` | 0 | |
| `imported` | 0 | |

**The provenance feature is entirely unexercised.** `source_type` exists to
record where a fact came from — HomeKit discovery, Matter, a human, an import —
and 100% of the development data says `generated`, because it came from
`populate_graph_db.py`. Nothing is wrong; it has simply never been used for its
purpose, which is worth knowing before building on it. This is the field most
likely to differ on the live instance.

---

## What this suggests

**Could create, cheaply:** `window` entities (`connects_to` already has rules
for them); `triggered_by` edges (rules exist, automations and schedules exist).

**Should decide:** the `contained_in` / `depends_on` gap; whether `located_in`
and `part_of` are one concept; whether `has_blob` should replace
`content.blob_id` or be deleted; whether the `app` feature is wanted.

**Worth measuring:** the same table against the live instance. Five of the
fourteen relationship types and two of the twelve entity types have no
development instances at all, and a vocabulary carrying ~35% unused surface is
either aspirational or has features nobody found.

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

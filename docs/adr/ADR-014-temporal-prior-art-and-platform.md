# ADR-014: Prior art for the temporal model, and whether the platform is right

**Status:** Accepted · 2026-08-23 · A **research record**, not a change of
direction. It ratifies ADR-004/005/009 by checking them against the literature
and against measurement, and it writes down the triggers that would overturn
them. Nothing here asks for code.

## Context

ADR-004 gave edges valid-time intervals and defined `snapshot(T)`. Four
questions were put to that design after it landed, and none of them had been
asked before the code was written:

1. Did we invent something that already exists?
2. Does Neo4j — or anything else — give this away for free?
3. Is the implementation efficient at the scale we actually want?
4. Is Python the right language, versus Go or Rust?

The honest answer to (1) is **no, we invented nothing**, and that is the most
useful finding in this document: the design has an established name, a
standard, and a body of research that tells us which parts are load-bearing.

## Decision

Keep the design, keep SQLite, keep Python. Adopt the standard's *vocabulary*.
Record the triggers below rather than revisiting any of it on feeling.

---

## 1. We reinvented the Bitemporal Conceptual Data Model

The model ADR-004 describes was defined by **Richard Snodgrass and Christian
Jensen in 1994** as the Bitemporal Conceptual Data Model, and became the basis
of **ISO SQL:2011**'s temporal features. The correspondence is not loose:

| ADR-004 calls it | The literature calls it |
|---|---|
| `valid_from` / `valid_to` on an edge | valid time; `val-from` / `val-to` |
| server apply order (`server_seq`) | transaction time; `tx-from` / `tx-to` |
| §3 `snapshot(at)` | the **Snapshot** operator |
| §3's "`diff(T1,T2)` falls out nearly free" | the **Diff** operator |
| "bitemporal-lite" (§Alternatives) | valid-time state table + transaction-time audit |
| edges as interval rows | the **Valid Edge Representation** |

That last row matters. The survey literature names exactly three ways to
represent a temporal graph — *Sequential*, *Snapshot*, and *Valid Edge* — and
ADR-004 §1 picked the third without knowing it had a name. The **Temporal
Property Graph Model** (TPGM) behind Leipzig's Gradoop is the same design
generalised: bitemporal `val-from`/`val-to` and `tx-from`/`tx-to` on every
vertex and edge, with Snapshot, Diff and Grouping as its named operators.

**Two deliberate deviations, both already argued in ADR-004:**

- **We are not fully bitemporal.** Vertices carry valid time implicitly (the
  version string) rather than as an interval pair, and transaction time exists
  only for replication. The literature's justification for full bitemporality is
  *retroactive correction of recorded history* — Snodgrass's motivating use
  case. Nothing in this system edits the past; it only queries it. ADR-004's
  "bitemporal-lite" is a recognised, defensible point on that spectrum, not a
  shortcut.
- **Our intervals are half-open** `[valid_from, valid_to)`. This matches
  SQL:2011's `PERIOD FOR` convention, and for the same reason we found
  empirically when writing the handover test: closed-open is what makes ending
  one interval and starting its successor at the same instant yield exactly one
  current edge.

**What this buys us going forward:** ADR-004 §3 is unbuilt, and it should now be
built to the standard's vocabulary rather than to invented names — `AS OF`
rather than `at=`, and `snapshot` / `diff` as the operator names, because they
already mean this to anyone who has read the literature or used XTDB.

## 2. Neo4j would not have given us this

Neo4j has **temporal data types** — `Date`, `DateTime`, `Duration` and friends,
since 3.4. That is a type system for storing timestamps. It is not time travel,
and the two get conflated constantly.

For the thing ADR-004 actually does, Neo4j has **no built-in support**: you
model versioning yourself, exactly as we did. What exists around it:

- **Versioner-core**, a community plugin offering some automated versioning.
- **NEP-001**, a community proposal for native bitemporal graph support with a
  reference implementation (`temporal.activeAt`, `temporal.asOf.relationships`,
  `temporal.asOf.traverse`). A proposal with a prototype, not shipped Neo4j.
- **Aion** (EDBT 2024, with a Neo4j-affiliated author), a research system that
  bolts a hybrid `GraphStore` / `TimeStore` / `LineageStore` onto Neo4j —
  time-indexed updates for whole-graph restoration at an arbitrary instant, plus
  entity-indexed updates for fine-grained history. *(Cited from its abstract;
  the PDF did not extract, so no performance claim is repeated here.)*

That Aion exists at all is the finding. If temporal graph management were solved
inside Neo4j, a 2024 research paper would not be adding three stores to it.

**Conclusion:** adopting Neo4j would have moved the same modelling work behind a
much heavier dependency, and would have broken ADR-001's single-file backup and
ADR-009's replicate-to-the-client requirement outright.

## 3. Systems that *do* give it away — and why we still should not switch

Four are genuinely close to what we built:

- **XTDB v2** — bitemporal by default on every row, no extra columns to
  maintain, SQL:2011 `AS OF` over the Postgres wire protocol. This is the
  closest thing to "our ADR-004 as a product".
- **Datomic** — immutable facts, one transactor serialising writes, peers
  reading coherent snapshots, `as-of` to rewind.
- **Dolt** — Git semantics on table rows; `AS OF` against commits, cell-wise
  diff and merge.
- **TerminusDB** — immutable delta layers, branch/diff/merge/clone, instant
  time travel.

We should not adopt any of them, and the reason is **ADR-009**, not inertia. The
client is a *replica that answers as-of queries locally, offline*. That requires
the same temporal model on both sides, embedded in a phone-class client. XTDB,
Datomic, TerminusDB and Dolt are all servers. Choosing one would give us
excellent temporal queries on the server and leave the client — where the
queries are actually made — with nothing, which is the arrangement ADR-009
exists to reject. Add ADR-001's constraints (single-file consistent backup, one
process per home on a Mac mini under launchd) and SQLite remains the only
option that satisfies all of them.

The cost of that choice is explicit: **SQLite implements none of SQL:2011's
temporal features**, so `snapshot(T)` is ours to write. Table stakes for
embedding; worth naming rather than discovering later.

## 4. Is the implementation efficient at our scale? — measured, not asserted

Live instance today: **423 entities · 510 version rows · 461 edges · 5.7 MB**.
ADR-001's honest worst case for the larger use cases: **~20k entities, ~150k
edges, ~365k version rows** accumulated over years.

A synthetic database was built at that worst case with this schema and these
indexes (30% of edge intervals retired, mirroring a house that gets
rearranged), and the queries the design depends on were timed:

| query | at worst-case scale |
|---|---|
| current graph, `valid_to IS NULL` (what GraphIndex loads) | **28.6 ms** |
| current entities, `is_latest` | **3.4 ms** |
| `snapshot(T)` edges — ADR-004 §3 | **51.4 ms** |
| `snapshot(T)` entities — max version ≤ T | **16.9 ms** |
| one edge's full history | **< 0.1 ms** |
| delta page by `server_seq` cursor | **0.1 ms** |

Database size at that scale: **132.8 MB** — under the ADR-007 500 MB tripwire,
which is therefore still the right alarm.

**Conclusion: the design is nowhere near being the constraint.** A full as-of
snapshot of a house 40× larger than the live one costs ~68 ms of query time.
ADR-004 §3's plan — SQL snapshot plus a transient in-memory index built at T —
is sound, and its "milliseconds at this scale" claim is now measured rather
than asserted.

**Caveats, stated so the numbers are not over-read:** synthetic and uniformly
distributed; single reader, no write contention; SQLite query time only, not
end-to-end API latency; and it does not model the Python-side cost of turning
those rows into objects, which §5 argues is the real ceiling.

**The one thing the literature warns about that we have not done:** our only
temporal index is `ix_rel_current` on `valid_to` plus `ix_rel_id_validity`.
`snapshot(T)` is a range scan over the interval columns — visible in the table
above as the slowest query by 2×. Systems built for temporal workloads at
serious scale (Aion's TimeStore, Clock-G) index the time dimension itself. At
150k edges a range scan is the right call; at 100× that it would not be.

## 5. Python is the right language, and the evidence is in §4

The question is usually argued on language benchmarks. It should be argued on
where the time actually goes.

**Against:** Rust is roughly 2× Go and far ahead of Python on CPU-bound work.
That is real and not disputed here.

**Why it does not apply:** §4 shows the heaviest temporal query at our worst
case is ~51 ms, and essentially all of it is inside SQLite's C implementation —
B-tree traversal and row decoding. Rewriting the caller in Go or Rust makes the
part that is already ~0 faster. For I/O-and-database-bound services the language
difference collapses; this is such a service, at a scale three to five orders of
magnitude below any engine limit.

**The measured counter-example makes the point better than the benchmark does.**
The one real performance defect found this month was not Python being slow. The
Python client rewrote and `fsync`ed its entire JSON store *once per applied
row*, so a sync of ~85 rows did ~340 fsyncs and blew through a 5-second timeout.
The fix was to batch the writes. A Go or Rust client with the same algorithm
would have been just as slow, and the actual repair — one store rewrite per
batch — was a dozen lines in the language we already use.

**What we would pay to switch:** the FastAPI/MCP ecosystem; `inbetweenies`,
which is a *shared* package imported by the server and the Python client alike,
so a rewrite is two rewrites; and single-maintainer familiarity across two
controlled installs. Against a benefit §4 measures as approximately zero.

**Triggers that would reopen this**, so it is a decision and not a habit:

- A single as-of query has to materialise a snapshot large enough that building
  Python objects, rather than running the SQL, dominates the response.
- Concurrency stops being one writer — ADR-005 §5 already names multi-server as
  the HLC trigger, and it is the same trigger here.
- The 500 MB tripwire (ADR-007) fires, since that is the point at which the
  storage assumptions get re-derived anyway.

Note that the *client* is the likelier candidate than the server, and the
likelier reason is a JSON document store rather than the language.

## Consequences

- ADR-004 §3, when built, uses SQL:2011 vocabulary: `AS OF`, `snapshot`, `diff`.
  Free comprehension for anyone who has met the standard, and it stops us
  inventing a third name for a thirty-year-old idea.
- ADR-004's "bitemporal-lite" gets a citation instead of an apology. The reason
  full bitemporality exists — retroactive correction — is a use case we do not
  have, and that is now written down.
- The 500 MB tripwire is confirmed as the right alarm: 132.8 MB at the projected
  worst case leaves real headroom.
- Temporal indexing is recorded as the first thing to add if scale ever grows by
  ~100×, with the systems that did it named.
- Python stays, with triggers rather than a promise.

## Alternatives considered

- **Adopt XTDB and delete our temporal code.** The strongest candidate by far —
  it is our design, productised and standard-compliant. Rejected on ADR-009: it
  cannot run inside the offline client, so it would solve the easy half of the
  problem and leave the half that matters.
- **Adopt Neo4j.** Would not have supplied the temporal model (§2), and breaks
  ADR-001's backup and deployment constraints.
- **Go full bitemporal now**, matching TPGM exactly. Rejected: the extra two
  columns per row exist to support retroactive correction, which nothing asks
  for. Revisit if the requirement ever appears — the migration is additive.
- **Rewrite the server in Go or Rust.** Rejected on measurement (§5), not on
  preference. The triggers are recorded.
- **Write nothing down and move on.** Rejected because the questions in the
  Context are good ones that will be asked again, and answering them from
  memory a second time would produce a different answer.

## Sources

Neo4j and temporal graphs: [What Neo4j Temporal actually does](https://hoop.dev/blog/what-neo4j-temporal-actually-does-and-when-to-use-it) ·
[Keeping track of graph changes using temporal versioning](https://medium.com/neo4j/keeping-track-of-graph-changes-using-temporal-versioning-3b0f854536fa) ·
[Aion: Efficient Temporal Graph Data Management (EDBT 2024)](https://openproceedings.org/2024/conf/edbt/paper-124.pdf) ·
[Time & Versioning in Graphs](https://gist.github.com/imranansari/1fb97b6137b88b5d2a36e00b901eff15)

Bitemporal model and the standard: [XTDB — Time in XTDB](https://docs.xtdb.com/about/time-in-xtdb.html) ·
[XTDB v2 launch](https://xtdb.com/blog/launching-xtdb-v2) ·
[SQL:2011 (Wikipedia)](https://en.wikipedia.org/wiki/SQL:2011) ·
[Temporal features in SQL:2011 (ULB)](https://cs.ulb.ac.be/public/_media/teaching/infoh415/tempfeaturessql2011.pdf) ·
[Survey of SQL:2011 Temporal Features](https://illuminatedcomputing.com/posts/2019/08/sql2011-survey/)

Temporal graph research: [Towards Temporal Graph Databases](https://arxiv.org/pdf/1604.08568) ·
[A model and query language for temporal graph databases (VLDB J.)](https://link.springer.com/article/10.1007/s00778-021-00675-4) ·
[Distributed temporal graph analytics with GRADOOP](https://old.dbs.uni-leipzig.de/file/Rost2021_Article_DistributedTemporalGraphAnalyt.pdf) ·
[Bitemporal Property Graphs: Dealing with Both Valid and Transaction Time](https://link.springer.com/chapter/10.1007/978-3-032-05281-0_15) ·
[Storing and Querying Evolving Graphs in NoSQL Storage Models](https://arxiv.org/pdf/2504.17438)

Comparable systems: [Datomic — time-traveling data](https://medium.com/cmcc-deepdive/5-datomic-time-traveling-data-immutable-semantics-804ae7f6ec05) ·
[Dolt — So you want a Temporal Database?](https://www.dolthub.com/blog/2023-08-07-temporal-database/) ·
[TerminusDB — immutability](https://terminusdb.org/docs/immutability-explanation/)

Language choice: [Go vs Python vs Rust — benchmarks and trade-offs](https://dev.to/pullflow/go-vs-python-vs-rust-which-one-should-you-learn-in-2025-benchmarks-jobs-trade-offs-4i62) ·
[Benchmarking SQLite performance in Go](https://www.golang.dk/articles/benchmarking-sqlite-performance-in-go)

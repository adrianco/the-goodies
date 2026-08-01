# ADR-007: Blobs move to content-addressed files; the database keeps metadata

**Status:** WITHDRAWN · 2026-08-01 — owner decision: blobs stay in-row. Single-file consistent backup is valued above the externalization benefits, and current volume (1 blob, 5.7 MB database) doesn't threaten it. One residue adopted: a size tripwire — warn in logs/health when the database crosses 500 MB so the decision is revisited on evidence. The original proposal is preserved below for that future discussion; the schema already leaves the door open (`data` nullable, `server_url`, per-blob sync status).

## Context

`blobs.data` is `LargeBinary` in the SQLite row — photos and PDF manuals inline in the database file. Consequences compound: the DB file (and its WAL) grows with every scanned manual; every backup copy and iCloud mirror upload re-copies all binary history; a future full sync to mobile drags blobs through the JSON protocol (base64 inflation) or needs a side channel anyway. The model already anticipates externality: `data` is nullable with a `server_url` field ("can be null if not yet downloaded"), and sync tracks blob status separately — the design is half-externalized already.

## Decision

1. **Content-addressed blob store on disk:** `blobs/<sha256[0:2]>/<sha256>` beside the database. The `blobs` table keeps metadata (id, name, type, mime, size, checksum, sync status) and drops the `data` column; checksum *is* the storage key, giving free dedup and integrity verification.
2. **Small-blob exception:** ≤ 64 KB (thumbnails, QR codes) may stay in-row — one file-copy backup unit is worth preserving for tiny payloads. A single code path decides by size at write.
3. **HTTP transfer, not protocol payload:** blobs move over dedicated endpoints (`GET/PUT /blobs/{checksum}`, ranged), referenced from entity sync by checksum. The sync protocol carries metadata only — mobile clients fetch lazily, exactly what `BlobStatus.PENDING_UPLOAD`/`server_url` were reaching for.
4. **Backup/mirror jobs add the blob directory** as a second rsync-style unit (cheap: content-addressing makes it append-only in practice).
5. Migration: one script exports existing `data` blobs to files and rewrites rows (1 blob today; both installs controlled).

## Consequences

- Database size becomes a function of *structured* data only; ADR-004's retention math stays honest.
- Backups stop re-copying binaries that didn't change; iCloud mirror gets cheaper.
- Mobile sync payloads stay small; images arrive on demand with resumable ranged GETs.
- The filesystem is now part of the data's integrity story — the backup job must treat DB + blob dir as one snapshot set (checksums make verification trivial).

## Alternatives considered

- **Stay in-row** — simplest, and SQLite handles BLOBs fine, but every operational cost above scales with binary volume, which is the one dimension a "scan all the manuals" use case grows without bound.
- **Object storage (S3/R2)** — introduces a cloud dependency and credentials for a system whose value proposition includes local-first; `server_url` leaves the door open later without deciding now.

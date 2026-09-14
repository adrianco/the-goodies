#!/usr/bin/env python3
"""
fg_client_selftest.py — live gates for the MCP-backed FunkyGibbon client.

Runs against the real server with throwaway entities that are tombstoned at
the end. Every write is read back in a SEPARATE PROCESS: a same-request read
is exactly what made the pre-v0.5.0 rollback bug invisible.

    python3 .claude/scripts/fg_client_selftest.py
"""
import base64, io, json, os, subprocess, sys, traceback
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from fg_client import FGClient, FGError

PASS = FAIL = 0
def ok(m):  global PASS; PASS += 1; print(f"  PASS  {m}")
def bad(m): global FAIL; FAIL += 1; print(f"  FAIL  {m}")
def check(cond, m): (ok if cond else bad)(m)

def readback_other_process(entity_id):
    """Read an entity from a fresh interpreter — no shared connection, no cache."""
    code = ("import sys,json; sys.path.insert(0,%r); from fg_client import FGClient; "
            "print(json.dumps(FGClient().get_entity(%r)))") % (HERE, entity_id)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    return json.loads(out.stdout or "{}")

def tiny_jpeg():
    try:
        from PIL import Image
        buf = io.BytesIO(); Image.new("RGB", (48, 32), (30, 90, 200)).save(buf, "JPEG"); return buf.getvalue()
    except ImportError:
        # smallest valid JPEG (1x1) — embedded so the test has no dependency
        return base64.b64decode("/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=")

def main():
    fg = FGClient()
    cleanup = []   # (kind, id)
    baseline_rels = None
    try:
        print("== gate 1: transport =="); st = fg.get_statistics()
        check(isinstance(st.get("total_entities"), int) and st["total_entities"] > 0, f"get_statistics: {st.get('total_entities')} entities / {st.get('total_relationships')} relationships")
        baseline_rels = st.get("total_relationships")

        print("== gate 2: reads =="); rooms = fg.list_entities("room")
        check(len(rooms) > 0, f"list_entities(room) -> {len(rooms)}")
        r0 = rooms[0]; byname = fg.find_entity_by_name("room", r0["name"], strict=True)
        check(byname and byname["id"] == r0["id"], f"find_entity_by_name resolves {r0['name']!r} to the same id")
        check(fg.get_entity(r0["id"]).get("name") == r0["name"], "get_entity(id) matches list")
        check(fg.get_entity("00000000-0000-0000-0000-000000000000") == {}, "get_entity(unknown) -> {}")

        print("== gate 3: writes, read back in another process ==")
        n = fg.create_entity("note", "zz-selftest-note", {"body": "selftest", "aliases": []}); nid = n["id"]; cleanup.append(("entity", nid))
        rb = readback_other_process(nid); check(rb.get("id") == nid and rb.get("name") == "zz-selftest-note", "create_entity persisted (other process sees it)")
        fg.update_entity(nid, name="zz-selftest-note-2", content={"body": "v2", "aliases": []})
        rb = readback_other_process(nid); check(rb.get("name") == "zz-selftest-note-2" and rb.get("content", {}).get("body") == "v2", "update_entity persisted (other process)")
        fg.upsert_alias(nid, "alias-a"); fg.upsert_alias(nid, "alias-a"); fg.remove_alias(nid, "nope")
        rb = readback_other_process(nid); check(rb.get("content", {}).get("aliases") == ["alias-a"], "upsert_alias (deduped) / remove_alias")
        fg.set_status(nid, "inoperable", "selftest"); rb = readback_other_process(nid)
        check(rb.get("content", {}).get("status") == "inoperable" and rb["content"].get("status_reason") == "selftest", "set_status")
        hits = fg.search_entities("zz-selftest-note", "note"); check(any(h.get("id") == nid for h in hits), "search_entities finds it")

        print("== gate 4: photo round-trip ==")
        jpg = tiny_jpeg(); att = fg.upload_blob(nid, jpg, "selftest.jpg", "image/jpeg", "selftest photo")
        pid, bid = att.get("id"), att.get("blob_id"); check(bool(pid) and bool(bid), f"attach_photo -> entity {str(pid)[:8]} blob {str(bid)[:8]}")
        if pid: cleanup.append(("entity", pid))
        check(fg.get_blob_bytes(bid) == jpg if bid else False, "get_blob bytes identical to what was sent")
        rb = readback_other_process(pid) if pid else {}; check(rb.get("entity_type") == "photo", "photo entity readable in another process, type=photo")
        rels = fg.list_relationships(from_id=nid, rel_type="has_photo"); check(any(r.get("to_entity_id") == pid for r in rels), "has_photo edge exists note->photo")
        check(not any(r.get("relationship_type") == "has_blob" for r in fg.list_relationships(from_id=nid)), "no retired has_blob edge written")

        print("== gate 5: relationships, move (end + create), tombstone ==")
        dev = fg.create_entity("device", "zz-selftest-device", {"status": "operational"}); did = dev["id"]; cleanup.append(("entity", did))
        rooms2 = rooms[:2] if len(rooms) >= 2 else rooms * 2; ra, rb_ = rooms2[0]["id"], rooms2[1]["id"]
        rel1 = fg.create_relationship(did, ra, "located_in"); check(bool(rel1.get("id")), "create_relationship device located_in room A")
        cur = fg.list_relationships(from_id=did, rel_type="located_in"); check(len(cur) == 1 and cur[0]["to_entity_id"] == ra and not cur[0].get("valid_to"), "current located_in = A (open interval)")
        for r in cur: fg.end_relationship(r["id"], reason="selftest move")
        fg.create_relationship(did, rb_, "located_in")
        cur = fg.list_relationships(from_id=did, rel_type="located_in"); check(len(cur) == 1 and cur[0]["to_entity_id"] == rb_, "after move: current located_in = B only")
        hist = fg.list_relationships(from_id=did, rel_type="located_in", include_history=True); check(len(hist) == 2 and any(h.get("valid_to") for h in hist), "history keeps the ended A edge (valid_to set)")
        conn = fg.connected(did); check(any(c.get("id") == rb_ for c in conn), "connected(device) includes room B")
        devs = fg.list_devices_in_room(rb_); check(any(d["id"] == did for d in devs), "list_devices_in_room(B) includes the device")
        fg.delete_entity(did, reason="selftest cleanup", is_error=True)
        rb = readback_other_process(did); check(rb.get("content", {}).get("deleted") is True, "tombstone: deleted=true in another process")
        check(not any(d["id"] == did for d in fg.list_entities("device")), "tombstoned device absent from list_entities")
        # Keep did in `cleanup` (re-tombstone is idempotent) so the cleanup phase
        # also ends its still-open located_in edge — tombstoning left it dangling.

        print("== gate 6: vocabulary (informational) ==")
        for et in ("app", "automation", "home"):
            try:
                e = fg.create_entity(et, f"zz-selftest-{et}", {}); cleanup.append(("entity", e["id"])); print(f"  info  entity_type {et!r}: accepted")
            except FGError as ex: print(f"  info  entity_type {et!r}: REFUSED — {str(ex)[:90]}")
        try:
            d2 = fg.create_entity("device", "zz-selftest-btn", {}); cleanup.append(("entity", d2["id"]))
            d3 = fg.create_entity("device", "zz-selftest-keypad", {}); cleanup.append(("entity", d3["id"]))
            fg.create_relationship(d2["id"], d3["id"], "part_of"); print("  info  device part_of device: accepted")
            fg.create_relationship(d2["id"], d3["id"], "controls"); print("  info  device controls device: accepted")
        except FGError as ex: print(f"  info  edge refused — {str(ex)[:100]}")
    except Exception:
        bad("unexpected exception"); traceback.print_exc()
    finally:
        print("== cleanup ==")
        # Tombstoning an entity does NOT end its edges (they keep an open interval
        # pointing at a deleted endpoint), so end every throwaway's relationships
        # in BOTH directions before tombstoning it — otherwise the graph's
        # relationship count drifts upward on every run (the-goodies#96).
        ended = 0
        for kind, eid in cleanup:
            for finder in (dict(from_id=eid), dict(to_id=eid)):
                try:
                    for r in fg.list_relationships(**finder):
                        if r.get("valid_to"):
                            continue  # already ended (e.g. the gate-5 move)
                        try: fg.end_relationship(r["id"], reason="selftest cleanup"); ended += 1
                        except Exception as ex: print(f"  warn  could not end edge {str(r.get('id'))[:8]}: {ex}")
                except Exception as ex: print(f"  warn  could not list edges for {eid[:8]}: {ex}")
        for kind, eid in cleanup:
            try: fg.delete_entity(eid, reason="selftest cleanup", is_error=True)
            except Exception as ex: print(f"  warn  could not tombstone {eid[:8]}: {ex}")
        print(f"  ended {ended} edges, tombstoned {len(cleanup)} throwaway entities")
        # Gate 24: the graph is back exactly where it started — no relationship creep.
        if baseline_rels is not None:
            final_rels = fg.get_statistics().get("total_relationships")
            check(final_rels == baseline_rels,
                  f"relationship count restored to baseline ({baseline_rels}); after cleanup = {final_rels}")
    print(f"\n--- {PASS} passed, {FAIL} failed ---"); return 0 if FAIL == 0 else 1

if __name__ == "__main__":
    sys.exit(main())

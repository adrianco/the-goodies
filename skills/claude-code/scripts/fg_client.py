#!/usr/bin/env python3
"""
fg_client.py — FunkyGibbon client over the MCP tool surface.

the-goodies v0.7.0 removed the graph REST API (ADR-015): MCP is the client
interface. Every call here is `POST /api/v1/mcp/tools/<tool>` with
`{"arguments": {...}}` and a bearer token, so scripts get the same 23-tool
catalog KittenKong serves over stdio — without KittenKong in the loop.

The public method names are kept from the old REST client so room_commit,
app_commit and the skills keep working. Semantics that changed on purpose:

  * upload_blob   -> attach_photo / attach_document. The server creates the
                     `photo` (or `manual`) entity, stores the bytes content-
                     addressed, and links `has_photo` / `documented_by` in one
                     call. No more hand-rolled `is_blob` notes.
  * delete_entity -> tombstone_entity. Nothing is destroyed; a tombstone
                     version is appended and the entity drops out of listings.
  * delete_relationship -> end_relationship (ADR-004): the interval is closed,
                     the row is kept as history. A "move" is end + create.
  * source_type   -> the tool always records `manual`; the argument is accepted
                     and ignored so existing callers do not break.

Auth: FUNKYGIBBON_TOKEN, else the token setup_auth wrote to ~/.oook/config.json,
else the repo's .blowingoff.json. Never a password.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

SERVER_URL = os.environ.get("FUNKYGIBBON_URL", "http://localhost:8000")
PROJECT_DIR = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
_IMAGE_MIMES = ("image/jpeg", "image/png", "image/webp", "image/gif", "image/heic")


class FGError(Exception):
    pass


def _load_token() -> str:
    tok = os.environ.get("FUNKYGIBBON_TOKEN", "").strip()
    if tok:
        return tok
    for path, key in (
        (os.path.expanduser("~/.oook/config.json"), "auth_token"),
        (os.path.join(PROJECT_DIR, ".blowingoff.json"), "auth_token"),
        (os.path.join(PROJECT_DIR, "the-goodies", ".blowingoff.json"), "auth_token"),
    ):
        try:
            with open(path) as f:
                val = json.load(f).get(key, "")
            if val:
                return val
        except Exception:
            continue
    raise FGError(
        "No FunkyGibbon client token: set FUNKYGIBBON_TOKEN or run "
        "`python -m funkygibbon.setup_auth --client-token-only --jwt-secret …` in the-goodies-python"
    )


class FGClient:
    """FunkyGibbon over MCP tools. One instance per script run is fine."""

    def __init__(self, db_path: Optional[str] = None, server_url: str = SERVER_URL,
                 token: Optional[str] = None, user_id: str = "agent", timeout: float = 30.0):
        self._server_url = server_url.rstrip("/")
        self._token = token or _load_token()
        self._user_id = user_id
        self._timeout = timeout

    # ── transport ─────────────────────────────────────────────────────────

    def call(self, tool: str, **arguments: Any) -> Any:
        """Invoke one MCP tool; return its `result`. Raises FGError on any failure."""
        args = {k: v for k, v in arguments.items() if v is not None}
        req = urllib.request.Request(
            f"{self._server_url}/api/v1/mcp/tools/{tool}",
            data=json.dumps({"arguments": args}).encode(),
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as r:
                body = json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read() or b"{}").get("detail", "")
            except Exception:
                detail = ""
            if e.code == 401:
                raise FGError("FunkyGibbon rejected the client token (401) — re-mint it with setup_auth") from e
            raise FGError(f"{tool}: HTTP {e.code} {detail}".strip()) from e
        except urllib.error.URLError as e:
            raise FGError(f"FunkyGibbon unreachable at {self._server_url}: {e.reason}") from e
        if isinstance(body, dict) and body.get("success") is False:
            raise FGError(f"{tool}: {body.get('error')}")
        return body.get("result", body) if isinstance(body, dict) else body

    # ── entities ──────────────────────────────────────────────────────────

    def create_entity(self, entity_type: str, name: str, content: Optional[Dict[str, Any]] = None,
                      source_type: str = "manual", user_id: Optional[str] = None) -> Dict[str, Any]:
        """Create an entity. `source_type` is accepted for compatibility; the tool records `manual`."""
        res = self.call("create_entity", entity_type=entity_type.lower(), name=name,
                        content=content or {}, user_id=user_id or self._user_id)
        return res.get("entity", res)

    def get_entity(self, entity_id: str, include_relationships: bool = False) -> Dict[str, Any]:
        """Latest version of an entity, or {} if it does not exist."""
        try:
            res = self.call("get_entity_details", entity_id=entity_id,
                            include_relationships=include_relationships or None)
        except FGError as e:
            if "not found" in str(e).lower():
                return {}
            raise
        ent = res.get("entity", res)
        if include_relationships and isinstance(ent, dict):
            ent = dict(ent)
            ent["relationships"] = res.get("relationships", [])
        return ent

    def update_entity(self, entity_id: str, name: Optional[str] = None,
                      content: Optional[Dict[str, Any]] = None, **_kwargs: Any) -> Dict[str, Any]:
        """Append a new version with the given changes; returns the re-read entity."""
        changes: Dict[str, Any] = {}
        if name is not None:
            changes["name"] = name
        if content is not None:
            changes["content"] = content
        if not changes:
            return self.get_entity(entity_id)
        self.call("update_entity", entity_id=entity_id, changes=changes, user_id=self._user_id)
        return self.get_entity(entity_id)

    def delete_entity(self, entity_id: str, reason: Optional[str] = None,
                      is_error: bool = False) -> Dict[str, Any]:
        """Tombstone: appends a `deleted: true` version. History is kept."""
        return self.call("tombstone_entity", entity_id=entity_id,
                         reason=reason or "removed via house agent", is_error=is_error,
                         user_id=self._user_id)

    def list_entities(self, entity_type: Optional[str] = None, page_size: int = 100,
                      include_decommissioned: bool = False) -> List[Dict[str, Any]]:
        """All current (non-tombstoned) entities of a type, auto-paginated."""
        out: List[Dict[str, Any]] = []
        offset = 0
        while True:
            try:
                res = self.call("list_entities", entity_type=(entity_type or "").lower() or None,
                                limit=page_size, offset=offset)
            except FGError as e:
                # An undeclared type is a vocabulary refusal, not "no rows" — surface it.
                raise
            batch = res.get("entities") or []
            out.extend(batch)
            offset += len(batch)
            if len(batch) < page_size or offset > 50_000:
                break
        if not include_decommissioned:
            out = [e for e in out if (e.get("content") or {}).get("status") != "decommissioned"]
        return out

    def find_entity_by_name(self, entity_type: str, name: str, strict: bool = False) -> Optional[Dict[str, Any]]:
        candidates = self.list_entities(entity_type)
        norm = name.strip().lower()
        for e in candidates:
            if (e.get("name") or "").strip().lower() == norm:
                return e
        if strict:
            return None
        matches = [e for e in candidates if norm in (e.get("name") or "").lower()]
        return matches[0] if len(matches) == 1 else None

    def find_entities_by_name(self, entity_type: str, name: str) -> List[Dict[str, Any]]:
        norm = name.strip().lower()
        return [e for e in self.list_entities(entity_type) if norm in (e.get("name") or "").lower()]

    def search_entities(self, query: str, entity_type: Optional[str] = None,
                        limit: int = 20) -> List[Dict[str, Any]]:
        res = self.call("search_entities", query=query,
                        entity_types=[entity_type.lower()] if entity_type else None, limit=limit)
        items = res.get("results") or []
        return [r["entity"] if isinstance(r, dict) and "entity" in r else r for r in items]

    def get_entity_versions(self, entity_id: str) -> List[Dict[str, Any]]:
        res = self.call("get_entity_versions", entity_id=entity_id)
        return res.get("versions") or res if isinstance(res, list) else res.get("versions") or []

    # ── relationships ─────────────────────────────────────────────────────

    def create_relationship(self, from_id: str, to_id: str, relationship_type: str,
                            properties: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        res = self.call("create_relationship", from_entity_id=from_id, to_entity_id=to_id,
                        relationship_type=relationship_type.lower(), properties=properties)
        return res.get("relationship", res)

    def list_relationships(self, from_id: Optional[str] = None, to_id: Optional[str] = None,
                           rel_type: Optional[str] = None, include_history: bool = False) -> List[Dict[str, Any]]:
        res = self.call("list_relationships", from_entity_id=from_id, to_entity_id=to_id,
                        relationship_type=(rel_type or "").lower() or None,
                        include_history=include_history or None)
        return res.get("relationships") or []

    def end_relationship(self, relationship_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        """Close the edge's interval (ADR-004). The row stays as history."""
        return self.call("end_relationship", relationship_id=relationship_id, reason=reason,
                         user_id=self._user_id)

    delete_relationship = end_relationship  # compatibility name

    def connected(self, entity_id: str, rel_type: Optional[str] = None,
                  direction: str = "both") -> List[Dict[str, Any]]:
        res = self.call("get_connected", entity_id=entity_id,
                        relationship_type=(rel_type or "").lower() or None, direction=direction)
        out = []
        for c in res.get("connected") or []:
            out.append(c.get("entity", c) if isinstance(c, dict) else c)
        return out

    # ── convenience ───────────────────────────────────────────────────────

    def get_home(self) -> Optional[Dict[str, Any]]:
        homes = self.list_entities("home")
        return homes[0] if homes else None

    def list_rooms(self) -> List[Dict[str, Any]]:
        return self.list_entities("room")

    def _from_entities(self, rels: List[Dict[str, Any]], want_type: str) -> List[Dict[str, Any]]:
        out = []
        for r in rels:
            fid = r.get("from_entity_id")
            if not fid:
                continue
            ent = self.get_entity(fid)
            if ent and ent.get("entity_type") == want_type and not (ent.get("content") or {}).get("deleted"):
                out.append(ent)
        return out

    def list_devices_in_room(self, room_id: str) -> List[Dict[str, Any]]:
        return self._from_entities(self.list_relationships(to_id=room_id, rel_type="located_in"), "device")

    def list_doors_for_room(self, room_id: str) -> List[Dict[str, Any]]:
        return self._from_entities(self.list_relationships(to_id=room_id, rel_type="connects_to"), "door")

    def get_statistics(self) -> Dict[str, Any]:
        return self.call("get_statistics")

    # ── attachments ───────────────────────────────────────────────────────

    def upload_blob(self, parent_entity_id: str, data: bytes, filename: str,
                    mime_type: str = "application/octet-stream",
                    description: Optional[str] = None) -> Dict[str, Any]:
        """Attach bytes to an entity. Images -> a `photo` entity linked by `has_photo`;
        PDFs -> a `manual` entity linked by `documented_by`. Returns a dict whose
        `id` is the attachment ENTITY id and `blob_id` the content-addressed blob."""
        if mime_type in _IMAGE_MIMES or mime_type.startswith("image/"):
            tool = "attach_photo"
        elif mime_type == "application/pdf":
            tool = "attach_document"
        else:
            raise FGError(f"upload_blob: unsupported mime type {mime_type!r} (images and PDFs only)")
        res = self.call(tool, parent_entity_id=parent_entity_id, filename=filename,
                        data_b64=base64.b64encode(data).decode("ascii"),
                        mime_type=mime_type, description=description, user_id=self._user_id)
        out = dict(res)
        out.setdefault("id", res.get("attachment_id"))
        return out

    attach_photo = upload_blob

    def get_blob(self, blob_id: str, include_data: bool = False) -> Dict[str, Any]:
        return self.call("get_blob", blob_id=blob_id, include_data=include_data or None)

    def get_blob_bytes(self, blob_id: str) -> bytes:
        b = self.get_blob(blob_id, include_data=True)
        return base64.b64decode(b.get("data") or b.get("data_b64") or "")

    # ── content-patch helpers (used by room-edit) ─────────────────────────

    def _patch_content(self, entity_id: str, mutate) -> Dict[str, Any]:
        ent = self.get_entity(entity_id)
        if not ent:
            raise FGError(f"entity {entity_id} not found")
        content = dict(ent.get("content") or {})
        if mutate(content) is False:
            return ent
        return self.update_entity(entity_id, content=content)

    def upsert_alias(self, entity_id: str, alias: str) -> Dict[str, Any]:
        alias = alias.strip()
        def m(c):
            aliases = list(c.get("aliases") or [])
            if not alias or alias in aliases:
                return False
            aliases.append(alias); c["aliases"] = aliases
        return self._patch_content(entity_id, m)

    def remove_alias(self, entity_id: str, alias: str) -> Dict[str, Any]:
        def m(c):
            c["aliases"] = [a for a in (c.get("aliases") or []) if a != alias]
        return self._patch_content(entity_id, m)

    def set_status(self, entity_id: str, status: str, reason: Optional[str] = None) -> Dict[str, Any]:
        """status: 'operational' | 'inoperable' | 'unknown' | 'decommissioned'."""
        import time
        def m(c):
            c["status"] = status
            if status in ("inoperable", "decommissioned"):
                c.setdefault("status_since", time.strftime("%Y-%m-%d"))
                if reason:
                    c["status_reason"] = reason
        return self._patch_content(entity_id, m)

    def close(self) -> None:
        pass

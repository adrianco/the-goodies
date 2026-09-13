---
name: app-walk
description: Interactive app onboarding — catalog the devices, routines, and screens of a mobile/web app (Alexa, Tuya, Hayward Omni, HomeKit, etc.) through conversation and screenshots; stores results in FunkyGibbon knowledge graph.
metadata:
  user_invocable: "true"
---

# /app-walk

Catalog a smart home app by walking through it together. User opens the app, describes what they see, sends screenshots, and the agent records devices, routines, and instructions into the knowledge graph. Later, when anyone asks "how do I control the ice maker?", the answer is retrievable: "Alexa app → Devices → Ice Maker. There's also a 'Morning Ice' routine."

## When to use

- User says "let's onboard [App]" / "catalog the Alexa app" / "walk me through Tuya" / `/app-walk Alexa`
- User wants to document what a smart home app controls and how to use it
- After installing a new app or adding devices to an existing one
- Cross-reference: "what app controls the X?" → only works after apps are walked

## Required scripts

All under `.claude/scripts/` (copy them there from `skills/claude-code/scripts/`):
- `app_session.py` — session state management
- `app_commit.py` — apply session diffs to FunkyGibbon
- `fg_client.py` — FunkyGibbon client over MCP tools (the-goodies ≥ v0.7.0; the graph REST API no longer exists). Writes are tombstones/interval edges: nothing is ever destroyed.
- `image_compress.py` — downsample screenshots before storage
- `render_review.py` — review markdown; publishes to `REVIEW_POST_URL` if set, else writes a file

## Known apps and their ecosystems

| App | Ecosystem | Platform | What it controls |
|-----|-----------|----------|-----------------|
| Amazon Alexa | alexa | ios/android | Plugs, lights, routines, Echo devices |
| Apple Home / HomeKit | apple | ios/macos | Locks, lights, thermostats, sensors | `com.apple.home://` (NOT x-hm:// — that's for QR pairing only) |
| Tuya / Smart Life | tuya | ios/android | Smart plugs, bulbs, generic Tuya devices |
| Hayward Omni | hayward | ios | Pool equipment (pump, heater, lights, waterfalls) |
| Mitsubishi Comfort | mitsubishi | ios | Thermostats |
| Lutron | lutron | ios | Lighting scenes, shades |
| Google Home | google | ios/android | Nest devices, routines |
| Rheem EcoNet | rheem | ios | Water heaters |

For unknown apps, ask the user for the ecosystem and what it controls.

## The conversation shape

### Launching apps (optional)

If you maintain tappable launch links for apps (e.g. iOS Shortcuts with iCloud URLs), put them in a JSON file `{"<slug>": "<url>", ...}` and point `FG_APP_LAUNCH_URLS` at it; `app_session.get_launch_url(slug)` returns the link, or `None`, in which case just say "Open [App] on your phone".

---

### Phase 1 — Orient

1. **Identify the app**. Extract the app name from the user's message.
   - Check for an existing open session: `python3 .claude/scripts/app_session.py list`
   - If one exists for the same app: "You have a walk in progress for [App] from [date]. Resume it, or start fresh?"
   - Determine platform (iOS/Android/web) and ecosystem from the known apps table above, or ask.

2. **Create the session**:
   ```python
   from app_session import AppSession
   session = AppSession.create(app_name="Alexa", platform="ios", ecosystem="alexa")
   ```

3. **Check FunkyGibbon for existing knowledge** about this app:
   ```python
   import sys; sys.path.insert(0, '.claude/scripts')
   from fg_client import FGClient
   fg = FGClient()
   existing = fg.find_entity_by_name("app", "Alexa")
   ```
   If an existing app entity is found, tell the user: "FunkyGibbon already has an Alexa app record with N devices. We'll update it."

4. **Send the launch link** and orient the user:
   ```python
   launch_url = get_launch_url("alexa")  # use the matching slug
   # Then send on your messaging channel:
   # "Tap here to open Alexa: {launch_url}
   #  Once it's open, show me the devices list or a routine — screenshot or just describe."
   ```
   If `launch_url` is None, just say: "Open the Alexa app on your phone."

### Phase 2 — Discovery loop

Drive by user input. For each thing the user describes or screenshots:

**User sends a screenshot:**
- Read the image with the Read tool
- Identify the screen (devices list, routine editor, room view, etc.)
- Attach it: `session.attach_screenshot(source_path, screen_name="Devices List", description="Shows 12 devices")`
- Describe what you see and ask follow-up questions

**User describes a device the app controls:**
```python
session.add_diff({
    "action": "add_device",
    "device": {
        "name": "Ice Maker",          # as named in the app
        "app_path": "Devices → Ice Maker",   # where to find it in the app
        "control_type": "on_off",      # on_off | dimmer | thermostat | scene | custom
        "fg_entity_id": None,          # cross-ref to FunkyGibbon device (ask if known)
        "notes": "Shows as offline sometimes — needs power cycle",
    },
})
```

**User describes a routine/automation:**
```python
session.add_diff({
    "action": "add_routine",
    "routine": {
        "name": "Morning Ice",
        "trigger": "7:00 AM daily",
        "actions": ["Turn on Ice Maker"],
        "app_path": "More → Routines → Morning Ice",
        "devices_involved": ["Ice Maker"],
        "notes": "",
    },
})
```

**User explains how to do something in the app:**
```python
session.add_diff({
    "action": "add_how_to",
    "note": "To add a new device: tap + in the top right, select 'Add Device', choose brand.",
})
```

**Cross-reference to FunkyGibbon:**
When a device is mentioned, check FunkyGibbon for a matching entity:
```python
import sys; sys.path.insert(0, '.claude/scripts')
from fg_client import FGClient
fg = FGClient()
results = fg.search_entities("Ice Maker")
```
If found, confirm with the user: "Is the 'Ice Maker' in Alexa the same as [FunkyGibbon entity name]? I'll link them." Then set `fg_entity_id` in the device diff.

**Transcript logging** — after each exchange:
```python
session.log("user", "<what the user said>")
session.log("agent", "<what you said back>")
```

**Keep asking follow-up questions** to fill in the knowledge:
- "What other devices are in the Alexa app?"
- "Are there any routines that control the [device]?"
- "Is there anything tricky about using this app?"
- "What's the main thing you use this app for?"

Don't force the user through every device. When they say "that's it", "done", "wrap it up", move to Phase 3.

### Phase 3 — Review

1. **Post the review** — summarize what was captured:
   ```python
   # Build a markdown summary of what was collected
   devices_md = "\n".join(f"- **{d['name']}** at `{d['app_path']}`" for d in devices_list)
   routines_md = "\n".join(f"- **{r['name']}** ({r['trigger']})" for r in routines_list)
   md = f"# {session.app_name} App Walk Review\n\n## Devices ({len(devices_list)})\n{devices_md}\n\n## Routines ({len(routines_list)})\n{routines_md}"
   ```
   Publish it with `render_review.post_review(title, md)` (a URL if `REVIEW_POST_URL` is set, else a file) and send it to the user.

2. **Ask the user**: "Does this look right? Reply 'confirm' to save it, or tell me what to change."

### Phase 4 — Edit or Confirm

**If "confirm"**:
```bash
python3 .claude/scripts/app_commit.py <session_id>
```
Report result: "Saved the [App] app record — N devices, M routines, K screenshots."

**If changes requested**: update the relevant diffs, regenerate review, re-confirm.

**If "discard"**: `session.set_status("discarded")`.

### Phase 5 — Handoff

After commit:
- Record a brief summary wherever your agent keeps handoff notes (if it has them)
- Add a one-line entry to your agent's long-term memory, e.g. `2026-04-13: Living Room — catalogued 5 new devices, 1 keypad (6 buttons), 2 doors. Session abc123…`
- message the user the final summary

## Important constraints

- **Never commit without review + confirm.** Even if the user seems impatient.
- **Screenshots always compressed** before storage (`image_compress.compress_image`).
- **Cross-reference proactively** — every device mentioned should be checked against FunkyGibbon. The goal is a connected knowledge graph, not an isolated list.
- **Ask about routines** — this is often the most valuable knowledge. "What automations do you have set up in [App]?" is always worth asking.
- **Platform matters** — note whether the app is iOS-only, Android-only, or cross-platform. This affects whether other household members can use it.

## What success looks like

End of a successful walk:
- FunkyGibbon has an `app` entity for the app with devices, routines, and how-to notes
- Devices in the app have `fg_entity_id` cross-references where possible
- Screenshots are `photo` entities linked `has_photo` to the app entity
- A note entity captures the full conversation transcript
- Your agent's memory has a one-line log entry
- User got a confirmation message: "Saved [App] — N devices, M routines"

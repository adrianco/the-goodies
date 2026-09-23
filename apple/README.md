# Apple platforms — the iOS app and the macOS helper (ADR-022)

Everything Swift lives here, and nothing Swift lives anywhere else in the
repo. Nothing under `apple/` is built yet: this directory holds what was
**retained** from the previous attempts and the layout the new work goes into.

```
apple/
  README.md                  this file
  deployment/                retained from c11s-house-ios: the Apple deployment setup
  salvage/homekit/           retained from c11s-house-ios: HomeKit access code, for reference
  TheGoodiesKit/             (to come) Swift Package shared by both apps
  EckyThump/                 (to come) the macOS helper, Mac Catalyst  -- ADR-019
  Goodies/                   (to come) the iOS 27 app                  -- ADR-022
  Goodies.xcworkspace        (to come)
```

## What was retained, and why only this

The owner's decision (2026-09-23): merge the Swift work into this repo,
archive `adrianco/c11s-house-ios` and `adrianco/the-goodies-swift`, keep the
**deployment setup** from c11s-house-ios and its **HomeKit access code** as
reference, and **none of its code or UI** — the app is rethought from scratch.

### `deployment/`

| File | What it is |
|---|---|
| `C11SHouse.entitlements` | The entitlements the shipped app had: `com.apple.developer.homekit`, `weatherkit`, app sandbox, network client. HomeKit is the one the new app needs from day one. |
| `Info.plist` | The usage-description strings TCC shows (`NSHomeKitUsageDescription`, microphone, speech recognition, location). Rewrite the wording; keep the set — it is the consent surface ADR-019 §2 describes. |
| `build-settings.txt` | The signing and target settings pulled from the old `project.pbxproj`: bundle id `com.c11s.house` (to be renamed), development team, manual signing, device family, deployment target. The values that took effort to get right once. |
| `deployment-strategy.md` | The old build/TestFlight/App Store procedure. Its schemes and release cadence are a starting point; its content assumed a product, which this is not. |

The old `.xcodeproj` itself was **not** brought across: it references every
file of the old UI. The new workspace is created fresh with these settings.

### `salvage/homekit/`

`HomeKitService.swift`, `HomeKitCoordinator.swift`, `HomeKitModels.swift`
and their tests, from c11s-house-ios. Reference, not a target: they are not
compiled here. What is worth taking from them into `TheGoodiesKit`:

- the `HMHomeManager` authorization flow and delegate handling
  (`homeManagerDidUpdateHomes`, the authorization-status publisher), which is
  the part that is fiddly to get right;
- the walk over homes → rooms → accessories → services → characteristics
  into plain value types (`HomeKitModels.swift`), which is the shape the
  helper's HomeKit *proposal* (ADR-019 §3) needs;
- the protocol-based, mockable design and its tests.

What is not wanted: the "save as notes" persistence (the app had its own
notes store; here the output is a session-file proposal), and anything that
assumed the old UI.

## Where the old repos went

- `adrianco/c11s-house-ios` — **archived**. Its deployment setup and HomeKit
  code are above; its code and UI are not carried forward.
- `adrianco/the-goodies-swift` (WildThing) — **archived**. Untested and
  abandoned; ADR-019 is the Swift component and it is deliberately not a
  replica.

See ADR-022 for the decision, ADR-019 for the helper, ADR-020 for how the
apps hold credentials, ADR-021 for how they fit with the other clients.

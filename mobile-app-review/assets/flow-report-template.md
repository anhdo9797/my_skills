# <Flow name>

> `flows/<flow-id>` · <core | secondary> · <app name> v<version> · <platform> · captured <YYYY-MM-DD>

<!--
Write this file in the user's language; keep UI labels, prices, and package names
verbatim. Drop sections that don't apply rather than filling them with "N/A".

The point of this document is to answer "what does this feature actually do, and
what happens to the data" — not to re-list the UI. Screen inventories belong in
the screen reports; link to them from here.
-->

## 1. What this flow delivers

The job in one or two sentences, from the user's point of view. What do you put in,
what do you get out, and why would someone do this?

## 2. Entry points and preconditions

- **Entry points:** Home → `Scan`; also the FAB on History
- **Preconditions:** camera permission granted; onboarding completed; login *not*
  required (verified)
- **Screens involved:** [Home](../../report/home/README.md) →
  [Scan](../../report/home/scan_plant/README.md) →
  [Result](../../report/home/scan_plant/result/README.md)

## 3. The flow as a diagram

Generated from the transitions you recorded — don't hand-edit inside the markers:

```
changelock.py render-diagram --root <root> --scope flow --flow <flow-id> \
  --inject flows/<flow-id>/README.md
```

<!-- flow-diagram:flow-<flow-id> -->
<!-- /flow-diagram:flow-<flow-id> -->

Thick arrows are the happy path, dashed ones were not traversed. Protocol and
accuracy checklist: `references/user-flow-diagrams.md`.

## 4. Happy path, step by step

Numbered steps, each with what you did, what happened, how long it took, and the
screenshot that proves it. This is the heart of the document — spend words here.

1. Tap `Scan` on Home → camera opens immediately, no permission prompt (already
   granted in onboarding). ![](../../screenshots/flows/<flow-id>/01-camera.png)
2. Frame the subject, tap the shutter → freeze-frame + "Analyzing…" spinner, ~4 s.
   ![](../../screenshots/flows/<flow-id>/02-analyzing.png)
3. Result screen. Verbatim output:
   - Species: `Monstera deliciosa`
   - Health: `Healthy` · confidence `92%`
   - Three care tips, each expandable
   ![](../../screenshots/flows/<flow-id>/03-result.png)

## 5. Data lifecycle

| Stage | What happens | Evidence |
|---|---|---|
| Input | Live capture, emulator virtual scene, fixture `fixture-01-monstera.png` (received by the app at 960×1280); gallery import also available via the icon left of the shutter and tested with the same fixture | `01-camera.png` |
| Processing | Server-side — fails with "No connection" in airplane mode | `07-offline.png` |
| Output | species, health verdict, confidence %, 3 care tips | `03-result.png` |
| Persistence | Survives kill + relaunch; appears in History | `04-history.png` |
| Reuse | Also increments the "Scans" counter on Profile | `05-profile.png` |
| Ownership | Stored locally; no login required to view. Migration on login *not tested* | — |
| Deletion | Swipe-left on a History row deletes; the Profile counter does **not** decrease | `06-delete.png` |

## 6. Case matrix

| # | Case | Kind | Input | Expected | Observed | Evidence | Verdict |
|---|------|------|-------|----------|----------|----------|---------|
| 1 | Clear photo, known plant | happy | monstera leaf | species + health | as above | `03-result.png` | ✅ |
| 2 | Same photo twice | variant | identical | same answer | 92% then 88%, same species | `08-repeat.png` | ⚠️ non-deterministic |
| 3 | Out-of-domain subject | abuse | a hand | reject / low confidence | `Monstera deliciosa, 87%` | `09-hand.png` | ❌ no reject path |
| 4 | 4th scan of the day | boundary | any | paywall | paywall fires *after* capture | `10-paywall.png` | ✅ |
| 5 | Airplane mode | error | any | clear error | "No connection", retry button | `07-offline.png` | ✅ |

Kinds: `happy` · `variant` · `error` · `boundary` · `abuse` · `state`.
Verdicts: ✅ works as expected · ⚠️ works but notable · ❌ broken or wrong ·
`not tested`.

## 7. Gates and limits inside this flow

Free quota and how it's communicated, where exactly the paywall fires, what
requires login, anything that requires a permission. Link to
[monetization](../../analysis/monetization.md) rather than duplicating prices.

## 8. Findings

Bugs, inconsistencies, and surprises — with the exact repro steps. Separate what
you observed from what you conclude. Be concrete: "the same photo returns different
confidence values on repeat scans" beats "the AI seems unreliable".

## 9. Not tested / blocked

Cases you planned but couldn't run, what you attempted, and what would unblock
them. An honest gap here is worth more than a confident guess in section 6.

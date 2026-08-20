# <App name> — user flow

> `analysis/ux-flows.md` · <app name> v<version> · <platform> · captured <YYYY-MM-DD>
> Coverage: <N> screens documented, <M> of <T> flows finished

<!--
Write the prose in the user's language; keep UI copy, prices and package names
verbatim. The diagrams are generated — do not hand-edit inside the marker blocks:

  changelock.py render-diagram --root <root> --scope app --inject analysis/ux-flows.md
  changelock.py render-diagram --root <root> --scope flow --flow <id> --inject ...
  changelock.py render-diagram --root <root> --scope journey --inject ...

If a diagram is wrong, the recorded edge is wrong: fix it with `add-edge` and
re-render. Protocol and accuracy checklist: references/user-flow-diagrams.md.
Drop any section that has nothing real in it rather than writing "N/A".
-->

## 1. App map

How the app is wired: every documented screen and the transitions between them.
Thick arrows are the happy path, dashed arrows were not traversed.

<!-- flow-diagram:app -->
<!-- /flow-diagram:app -->

Two or three sentences the map doesn't say by itself: the navigation model (tabs,
stack, drawer), which cluster holds the value and which are supporting, anything
that surprised you about the shape.

## 2. First-run journey — install to first value

<!-- flow-diagram:journey -->
<!-- /flow-diagram:journey -->

- **Time to first value:** <seconds> from launch to the first real output
- **Cost to get there:** <N> taps, <N> screens, <N> permission prompts,
  <N> account requirements, <N> ads or upsells
- **Where a real person would drop off:** the specific step, and why

## 3. Core flow — <flow name>

<!-- flow-diagram:flow-<flow-id> -->
<!-- /flow-diagram:flow-<flow-id> -->

- **Repeat cost:** <N> taps and <seconds> once onboarding is done
- **Where the data lands:** <node>, and whether it survives a relaunch
- **What the shape shows:** the one or two things a reader gets from the diagram
  and could not get from the screen reports — see
  [the flow report](../flows/<flow-id>/README.md) for the full case matrix

Repeat this section per registered flow, core first.

## 4. Gates

Every hexagon in the diagrams above, in the order a user meets them.

| Gate | Where it fires | Trigger | Before or after the work? | Evidence |
|---|---|---|---|---|
| Paywall · 3 free scans/day | after capture, before result | 4th scan of the day | **after** — the photo is already uploaded | `10-paywall.png` |
| Login wall | `Sync` on Profile | any tap | before | `05-login.png` |

Prices and tiers live in [monetization](monetization.md) — link, don't duplicate.

## 5. Friction and dead ends

Concrete, reproducible observations only: steps that took more taps than they
needed, back behaviour that loses work, screens with no way forward, labels that
led somewhere else. Separate what you observed from what you conclude.

## 6. Unmapped

The dashed edges and blocked branches, named honestly: what you couldn't traverse,
what you tried, and what would unblock it (a test account, a paid tier, a device
capability). A reader who knows the edges of the map can use the rest of it.

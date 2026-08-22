---
name: mobile-app-review
description: >-
  Deep-dive teardown of any mobile app (iOS/Android) by actually driving it on a
  real device or emulator via the mobile-mcp MCP server. Researches the store
  listing, installs the app, then investigates it like a product analyst rather
  than a screenshotter: runs the app's core value flow end-to-end with real input
  (scan, search, order, generate...) — camera-driven flows included, which it
  runs for real by feeding fixture images into the camera instead of skipping
  them — traces where the resulting data goes and
  whether it persists, tests both success and failure cases for flows like login
  or checkout, produces data when a list is empty instead of reporting it as
  empty — and alongside that maps every screen with vision plus the
  accessibility tree into per-screen reports with embedded screenshots. Records
  every screen transition it actually traverses as it goes, so it can generate an
  accurate Mermaid user-flow diagram of the whole app (navigation map, per-flow
  flowchart, first-run journey) where every arrow traces back to a screenshot
  instead of a guess. Tracks
  progress in a changelock file so a review can be paused today and resumed
  tomorrow exactly where it stopped. Use this skill whenever the user wants to
  analyze, review, teardown, reverse-engineer, benchmark, test, or "study" a
  mobile app or a competitor app — including when they only say "phân tích app
  X", "review app X", "xem app X có gì", "app X hoạt động thế nào", "test luồng
  login của app X", "test luồng scan/camera của app X",
  "check the paywall / subscription tiers of X", "where does
  app X put its ads", "map the features of X", "vẽ userflow / sơ đồ luồng / user
  flow diagram của app X", "vẽ workflow của cả app", "map the navigation of X",
  "diagram how users move through X", or paste a Play Store / App Store
  link or a bundle id like com.example.app. Also use it to continue an unfinished
  review ("tiếp tục review app X", "resume the teardown").
compatibility: >-
  Requires the mobile-mcp MCP server (npx -y @mobilenext/mobile-mcp@latest) with
  at least one connected Android device/emulator or iOS simulator. Python 3 for
  the bundled changelock script. WebSearch/WebFetch for store research. Camera
  flows additionally need adb (Android) or xcrun (iOS) on PATH, an emulator whose
  back camera is set to virtualscene, and Pillow if the script should generate
  fixture images.
---

# Mobile App Review

You are doing what a sharp product analyst does when they get handed a competitor's
app: install it, **use it like a real person with a real goal**, and come back with
an account of what the app actually does, what it does with your data, where it
makes money, and where it breaks — with receipts (screenshots) for each claim.

Two things make the difference between this and a screenshot dump.

**First: you are a user, not a camera.** An app that scans a plant and reports its
health is not "a Home screen with a Scan button and a banner ad" — it's a pipeline
you have to actually run: take a real scan, read the real result, find out how long
it took, whether it worked offline, where the result was saved, and what happens on
the fourth scan when the free quota runs out. Most of the value in a review lives
inside the app's one core flow, and none of it is visible from the outside. The
thinking protocol for this is in `references/flow-investigation.md`, and it is the
most important file in this skill — read it before you explore.

**Second: you must not lose your place.** A real app has dozens of screens; you
will run out of context long before you run out of screens. So this skill is built
around a persistent `changelock.json` holding the flows and the queue of unexplored
screens, with the route to reach each one. Everything you finish gets written to
disk immediately. If the session dies, the next session reads the changelock and
picks up where it stopped.

## Conventions to follow throughout

**Report language mirrors the user's language.** If they wrote "phân tích app
ABC", every report file is in Vietnamese. If they wrote "analyze app ABC", it's
English. Screen names, element labels, package names, and file/folder names stay
in their original form either way — a Vietnamese report still calls the button
`Scan Plant` if that's what the app says.

**Android by default.** Only review iOS if the user asks for it, or if no Android
device is available. If they ask for both, do Android first, then iOS, then write
a comparison section.

**Depth on the core flow beats breadth over screens.** If you have budget for
twelve screens or for the core flow plus six screens, take the second every time.
A user can guess what a Settings screen contains; they cannot guess that the scan
takes four seconds, runs server-side, and paywalls *after* the photo is captured.
When in doubt about where to spend the next ten minutes, spend it going one step
deeper into what the app is *for*.

**An empty screen is a task, not a result.** Empty History, empty Favorites, empty
cart — that means you haven't produced the data yet. Do the work that fills it
(usually: run the core flow once), then document both the empty and the populated
state. The populated one is where sort, filter, swipe actions, item detail, and
in-list ads live, and none of it is visible while the list is empty. That's what
makes an empty-list report read as complete while covering nothing.
`references/flow-investigation.md` step 5 lists the ways to produce data, including
when live camera capture isn't available to you.

**A camera flow is not a blocked flow.** When the core flow runs through a
camera — scan, QR, OCR, document capture, try-on — you feed it a fixture image
rather than marking it untestable: the Android emulator can hang your own image
in front of the lens and swap it per case, every target can import from the photo
library, and a physical device can be pointed at a fixture displayed on screen.
`references/camera-flows.md` has the three routes and
`scripts/camera_fixture.py check` names the one your target supports. For a
scanner app this *is* the review; "camera opened, not tested further" is the
screenshotter's version of it.

**The map is a deliverable, and it gets built as you walk.** One of the review's
outputs is a diagram of how a person moves through the app, and the only way to
make it accurate is to record each transition at the moment you watch it happen —
one `add-edge` call with the screenshot that proves it. Reconstructed at the end
from memory, a flow diagram grows arrows nobody ever traversed, and a reader has no
way to tell those from the real ones. `references/user-flow-diagrams.md` has the
protocol; the diagram itself is generated from what you recorded, never drawn by
hand.

**Test success before you test failure.** For any flow with cases — login, signup,
checkout, search, upload — complete the happy path with valid input *first*, then
work outward to the ordinary mistakes a real person makes, then the edges. An error
catalogue with no success baseline can't distinguish "correctly rejected" from
"broken", and the user asked what the app *does*, which is a question only the
happy path answers.

**Enumerate before you act, and never claim what you didn't see.** These two are
the quality bar for the whole review. On every screen you produce a written
**Screen Read** (a complete enumeration of what's on screen) and a **Test Plan**
(what you'll probe and what question each probe answers) *before* tapping
anything — the protocol is in `references/screen-reading.md`. And every
behavioural statement in a report must trace back to something you actually
observed, with a screenshot to back it. If you didn't tap it, write "not tested"
rather than inferring from the label. A report that is 70% complete and fully
trustworthy is worth far more than one that reads as complete because the gaps
were filled with plausible guesses — the user cannot audit your guesses, only your
screenshots.

**Hard safety limits — these are not negotiable, because breaking them costs the
user real money or real data:**
- Never complete a purchase or subscription. Screenshot the paywall, record every
  tier and price, tap up to the point where the OS payment sheet appears, then
  cancel out. Never tap `Subscribe` → `Confirm`, never enter payment details.
- Never destroy state: no delete-account, no clear-data, no logout from an account
  the user owns, no uninstall, no factory reset.
- If a screen requires login and you have no credentials, mark that branch
  `blocked` in the changelock, note what's behind it, and move on. Ask the user
  once, at the end of the session, whether they want to supply a test account.

**Hard completeness limits — these exist because the two most common ways this
review goes wrong are silent, not loud: a screen gets described from an
inference instead of a look, or a flow gets called finished after only its easy
case.** The changelock enforces these mechanically, not just on the honor
system, because judgment erodes under context pressure exactly when it matters
most:

- `init` refuses to create a second folder for an app already under review, and
  refuses a root that isn't `<reviews-dir>/<slug>/<platform>` or a slug carrying a
  retry marker (`-fresh`, `-v2`, `-test`, `-copy`). A duplicate folder is the most
  expensive mistake in this skill: the screenshots, findings and diagram split
  across two trees and neither session can resume either.
- Report, screenshot and evidence paths are stored relative to the review root, and
  an absolute path or one that escapes the root is refused. Output that lands
  outside the root is invisible to the index and the diagram.
- `update-screen --status done` refuses a screen with zero screenshots attached.
  If a screen genuinely can't be captured, that's `blocked`, not `done`.
- `update-flow --status done` refuses a flow with no completed `happy` case, and
  flags (without blocking) a flow closed with *only* a happy case — most flows
  have an everyday failure or empty-result case (wrong input, no results,
  quota/paywall, offline) that a real user hits constantly, and it belongs in the
  case matrix before the flow counts as reviewed.
- `add-edge --status observed` refuses a transition with no `--evidence`. A
  transition you can't point at a screenshot for is indistinguishable from one
  you assumed.
- A wizard or stepper (onboarding, checkout, a multi-question form) is as many
  screens as it has steps, never one — see the near-match rule in
  `references/exploration.md`.

Each of these has a `--force` escape hatch for a genuine exception. Reaching for
it to get past the warning instead of doing the extra minute of work — one more
screenshot, one more case — defeats the entire point of having the guard.

## Workflow

Six phases. Phase 0–2 run once per app; phase 3 is the long loop; 4–5 close out.
The changelock records which phase you're in, so on resume you jump straight to
the right one.

### Phase 0 — Resolve the one folder (always first)

**One app + one platform = exactly one folder, for the whole life of the review.**
Before anything else, ask which folder this review belongs in — never guess a path
and never invent a new one:

```bash
python3 <skill-dir>/scripts/changelock.py resolve \
  --app-name "Spoonful" --platform android --package com.spoonful.app
```

The answer starts with one of two words, and it is not a suggestion:

- **`EXISTING <root>`** — this app is already under review, possibly filed under a
  different slug by an earlier session. That folder *is* the review. Run `status
  --root <root>`, print a short summary to the user (screens done, screens queued,
  where you left off) and jump straight to the phase it names. Do **not** run
  `init`. Do not re-run store research or re-explore finished screens — that's the
  entire point of the changelock. Only redo a screen if the app version changed or
  the user asks.
- **`NEW <root>`** — no review exists yet. Use *exactly* that root in Phase 2's
  `init`, unchanged.

`resolve` also derives the slug, deterministically, from the app name (`PlantID` →
`plantid`, `Spoonful: Eats` → `spoonful-eats`), so the same app always lands in the
same folder no matter how the request was phrased. Take the slug it gives you.

`changelock.py list` shows every review folder on disk and flags apps that
somehow ended up owning more than one — use it if you suspect a split.

### Phase 1 — Identify and research the app

The user gives you a name ("PlantID"), a bundle id (`com.example.plantid`), or a
store link. Resolve it into a concrete target:

1. Search the Play Store and App Store listing. Read `references/store-research.md`
   for exactly what to extract and where the useful signals hide.
2. Find and read the landing page / marketing site if one exists.
3. Write `00-overview/store-listing.md` and, if there is one,
   `00-overview/landing-page.md`.

This phase is cheap and it makes the whole review sharper: the store listing tells
you what the developer *thinks* the headline features are, and the pricing text in
the listing tells you which paywalls to hunt for later. Do it before touching the
device.

If the app name is ambiguous (several apps share it), show the user the top
candidates with developer name and install count and let them pick.

### Phase 2 — Get the app running

1. `mobile_list_available_devices` — pick the target. If several match the chosen
   platform, ask the user which one.
2. `mobile_get_screen_size` — store it in the changelock; you need it to reason
   about coordinates and to judge whether an element is "above the fold".
3. `mobile_list_apps` — is the target package already installed?
4. If not installed, open the store on-device and install through the UI:
   - Android: `mobile_open_url` with `market://details?id=<package>`
   - iOS: `mobile_open_url` with `itms-apps://apps.apple.com/app/id<appId>`
   Then drive the Install button and poll with screenshots until it becomes Open.
   Note that `mobile_install_app` only takes a local `.apk`/`.ipa` path — use it
   only if the user hands you a build file.
5. `mobile_launch_app` and record the app version (Android:
   `adb shell dumpsys package <pkg> | grep versionName`).
6. If the listing or the app name suggests a camera feature (scan, QR, OCR,
   "identify", "try on", document upload), check the camera now — before you plan
   the flow, because an AVD created with the camera switched off makes every
   camera case impossible, and that's a one-command fix:

   ```bash
   python3 <skill-dir>/scripts/camera_fixture.py check
   ```

   Then set it up per `references/camera-flows.md` and generate the fixture set.
   Doing this here rather than mid-flow saves an emulator cold boot later.

Initialize the workspace and changelock now, before exploring — at the root Phase 0
resolved, with the slug it derived, and nowhere else:

```bash
python3 <skill-dir>/scripts/changelock.py init \
  --root reviews/plantid/android \
  --app-name "PlantID" --slug plantid --platform android \
  --package com.example.plantid --device emulator-5554 \
  --screen-width 1080 --screen-height 2400 --lang vi
```

### Phase 3 — Overview, then the core flow, then screens

**This is the core of the skill and where most of your time goes.** The order below
is deliberate: sketch broadly, then go deep on what the app is *for*, then fill in
the map. Each stage makes the next one cheaper.

#### 3a. Overview pass (one shot, no depth)

Fresh-install the impression: walk onboarding **screenshotting every single
step**, not just the first one. This is the one moment in the whole review when
this state exists at all — a reinstall rarely reproduces it exactly, and it's the
raw material for the first-run journey diagram, so a step you don't capture now
is gone for good, not deferred to a later pass. A 3-step onboarding is 3
screenshots and 3 `add-edge --tag journey` calls, not one; onboarding steps
sharing a visual template (e.g. the same "single-choice card" layout asking
different questions) are still separate, once-only pieces of evidence — see the
near-match rule in `references/exploration.md` for why they must not be
collapsed. Then land on the main screen and open each top-level destination
(bottom tabs, hamburger, main CTAs) just far enough to name it — this second part
is a genuine skim, because those screens live in the app permanently and the
per-screen loop (3c) will revisit and inventory them properly. Produce
`00-overview/app-map.md`: the feature clusters, the navigation shape, first
impressions of where money is made, and — the part that drives everything after
this — **the app's core flow, named in one line**, plus the secondary flows worth
testing.

Then seed the changelock: register the flows with `add-flow` (core first), and
queue the top-level screens in review order.

Record this pass as edges while you do it (`add-edge --tag journey` for the
install → onboarding → first-value path, plain edges for the top-level
navigation). This is the only moment in the whole review when you see the app the
way a new user does — that state is unrecoverable an hour from now, and it's what
the first-run journey diagram is made of.

#### 3b. Core flow deep dive — do this before the screen loop

Read **`references/flow-investigation.md`** now, `set-phase --phase core-flow` so a
resumed session lands back here, then run the core flow for real:

> name the flow → complete the happy path end-to-end with real input → trace the
> data lifecycle (where did the result go? does it survive a relaunch? does it work
> offline?) → build the case matrix → execute it happy → variant → error →
> boundary → abuse → write `flows/<flow-id>/README.md`

Why before the screens, and not after: running the flow walks you through most of
the app's important screens anyway, and it **leaves data behind**. History, recent
rows, counters, and item-detail screens are all empty shells until the core flow
has run once. Doing screens first means visiting half of them twice.

Record the flow's transitions as you run it: `--spine` on the happy path so the
main route reads at a glance, `--condition` on the branches, `--cost` where you
timed something, and a `system`/`gate`/`store` node (`add-node`) wherever the flow
passes through something that isn't a screen — a server round-trip, a quota
paywall, the place the result gets saved. Those non-screen nodes are most of what
makes the flow diagram worth more than a sitemap.

Update the flow in the changelock (`update-flow`) after each case, the same
discipline as screens. `status` warns while a core flow is unfinished — that
warning means the review isn't yet usable, however many screens are done.

If the flow's input is a camera, read `references/camera-flows.md` alongside this
and run the fixture set: one canonical subject for the happy path, then the
repeat, alternative, out-of-domain and degraded variants for the case matrix.
Record which route produced each case — live capture and gallery import are
different findings, and writing up an import as a scan is exactly the kind of
claim the evidence rules forbid.

Secondary flows (login, upgrade, share, sync) get the same treatment, after the
screen loop or interleaved with it as budget allows. Their case matrices always
include the success path, not just the failures.

#### 3c. Per-screen loop

Three reference files govern this loop, and you need the first two before the
first screen:

- **`references/screen-reading.md`** — *how to look at a screenshot.* The six-zone
  sweep, the six analytical lenses, and the two artifacts you must produce for
  every screen before you touch anything: the **Screen Read** (everything visible,
  enumerated) and the **Test Plan** (what you'll probe, what question each probe
  answers, in priority order). This is the thinking part; read it first.
- **`references/exploration.md`** — *the mechanics.* Navigation by route, scroll
  capture, screen-signature dedupe that stops infinite loops, handling
  interstitials and permission dialogs, and recovery when you get stuck.
- **`references/user-flow-diagrams.md`** — *the map you build as a side-effect.* At
  minimum read its recording section before the first screen: the `add-edge` call
  belongs in this loop, and an edge not recorded here is one you'll be tempted to
  invent in Phase 4.

The loop in one line:

> navigate by route → screenshot → **Screen Read** → cross-check with
> `mobile_list_elements_on_screen` → **Test Plan** → scroll to capture the full
> screen → execute the plan by priority → write the screen report → queue newly
> discovered screens with their route → **record each transition you traversed
> (`add-edge`)** → back out → **update changelock**

Update the changelock after *every* screen, not at the end. A crash between
screens should cost you one screen, not the session.

Two rules from the flow work carry into every screen:

- **If a data-dependent screen is empty, filling it is part of the screen's work,**
  not a separate task to defer. Go produce the data (usually one run of the core
  flow), come back, and document both states. A screen report whose only content is
  "the list is empty" documents nothing.
- **If a screen turns out to be a step in a flow rather than a destination**
  (a camera view, a checkout step, a form), don't try to make a screen report carry
  it. Document the screen briefly and put the substance in the flow report, linked
  both ways.

While exploring, keep `references/monetization.md` in mind — ad slots and paywall
triggers are the highest-value findings and they're easy to miss if you're only
thinking about features. Read it before the first screen that shows an ad or a
premium prompt.

#### 3d. Budget and stopping

Stop the exploration loop and go to Phase 4 when any of these hit:
- The queue is empty and every registered flow is done (genuinely complete)
- ~15–20 screens covered this session, or your context is getting tight
- The user interrupts

If budget runs short with the core flow still unfinished, finish the flow and drop
screens. Screens are recoverable next session from the queue; a review that hands
back twenty screen reports and no idea whether the app's main feature works is not
recoverable — it's just wrong about what mattered.

Whichever it is, **always leave the changelock in a clean, resumable state** and
tell the user what remains. An honest "12 screens done, 7 queued, resume with
`tiếp tục review PlantID`" is far more useful than pretending it's finished.

### Phase 4 — Synthesis

Once exploration is done (or the session is ending with real coverage), write the
cross-cutting analysis. These are the files the user actually reads first:

- `analysis/feature-map.md` — the full feature tree with links into the per-screen
  reports, plus which features are free vs gated
- `analysis/monetization.md` — every ad placement (screen, position, format,
  trigger, frequency) and the complete subscription picture (tiers, prices, trial,
  where paywalls fire). Template and checklist in `references/monetization.md`.
- `analysis/ux-flows.md` — **the user-flow diagrams**, generated from the
  transitions you recorded, then annotated. Three of them: the app navigation map,
  one flowchart per flow (core first), and the first-run journey from install to
  first value. Around them goes what a diagram can't carry — time-to-first-value,
  the repeat cost of the core loop in taps and seconds, the gate table, and the
  friction. Start from `assets/user-flow-template.md`, follow
  `references/user-flow-diagrams.md`, and generate rather than draw:

  ```bash
  python3 <skill-dir>/scripts/changelock.py render-diagram --root <root> \
    --scope app --inject analysis/ux-flows.md
  python3 <skill-dir>/scripts/changelock.py render-diagram --root <root> \
    --scope flow --flow <flow-id> --inject analysis/ux-flows.md
  ```

  Each render lints the graph and prints what would make the diagram misleading —
  arrows without evidence, unreachable nodes, documented screens missing from the
  map. Fix those before you publish; they are precisely the things a reader can't
  catch on their own.
- `analysis/data-and-limits.md` — what the app does with user data across all
  flows: what's stored locally vs server-side, what survives a relaunch, what needs
  an account, what the free tier actually allows, and any behaviour that
  contradicts the store listing's claims. Write this only if the flow work
  produced enough substance; a thin version is worse than none.

### Phase 5 — Index and report back

```bash
python3 <skill-dir>/scripts/changelock.py render-index --root reviews/<app-slug>/<platform>
```

This regenerates `README.md` — the table of contents with flow and screen status
and a progress bar — from the changelock. Then give the user a short chat summary:

- **What the app actually does**, described through its core flow: what you put in,
  what came back, how long it took, where the result went. Lead with this — it's
  the answer to the question they asked.
- The 3–5 most interesting findings, including anything that surprised you or
  contradicted the store listing
- Monetization in two sentences
- A pointer to the app map in `analysis/ux-flows.md` — for most readers the diagram
  is the fastest way into everything else, so name it explicitly
- Coverage and honest gaps: which flows and cases you ran, what stayed blocked and
  why, and how to resume

## Output layout

Everything lives under the working directory, in **one folder per app + platform**.
That folder is created once, by Phase 2's `init`, at the root Phase 0 resolved; every
later session writes into the same tree. A second folder for the same app — a
`-fresh` sibling, a `-v2`, a slug spelled differently — is a bug, not a new review:
it re-shoots screenshots that already exist, and it strands half the findings where
neither the index nor the diagram can see them. `<app-slug>/<platform>` is the only
place a folder name is chosen; screens live under `report/` inside it, never as a
sibling of the app folder.

```
reviews/<app-slug>/<platform>/
├── changelock.json              # state: phase, flows, screens, queue, findings
├── README.md                    # generated index + progress
├── 00-overview/
│   ├── store-listing.md
│   ├── landing-page.md
│   └── app-map.md               # feature clusters + the named core flow
├── flows/
│   └── scan-plant/README.md     # the core flow: happy path, data, case matrix
├── report/
│   └── home/
│       ├── README.md            # the Home screen report
│       ├── profile/README.md    # reached from Home
│       └── scan_plant/README.md
├── fixtures/                    # camera fixtures, reused on resume
│   ├── manifest.json            # subject, expected answer, source, licence
│   └── fixture-01-monstera.png
├── screenshots/
│   ├── flows/scan-plant/01-camera.png
│   └── home/profile/01-initial.png
└── analysis/
    ├── feature-map.md
    ├── monetization.md
    ├── ux-flows.md
    └── data-and-limits.md
```

Screen paths nest to mirror navigation, so `report/home/profile/README.md` reads
as "Profile, reached from Home" — matching how the user thinks about the app.
Screenshots mirror the same path so relative links from a report are always
`../../screenshots/<path>/<file>.png`.

Flow reports are organised by flow rather than by navigation, because a flow
crosses several screens and no single screen report can hold it. Cross-link them:
each participating screen report points at the flow, and the flow points back.

Two templates, both starting points rather than cages — drop sections that don't
apply rather than filling them with "N/A":

- `assets/screen-report-template.md` — per-screen inventory and behaviour
- `assets/flow-report-template.md` — happy path, data lifecycle, case matrix
- `assets/user-flow-template.md` — the diagram sections with their generator
  markers, plus the journey, gate and friction prose around them

## Changelock script

`scripts/changelock.py` owns all state mutation so you never hand-edit JSON:

| Command | What it does |
|---|---|
| `resolve` | Phase 0: name the one folder this app+platform belongs in (`EXISTING`/`NEW`) |
| `list` | List every review folder on disk and flag apps owning more than one |
| `init` | Create the folder tree and a fresh changelock, at the resolved root only |
| `status` | Human-readable progress; use on resume and when reporting |
| `next` | Pop the next queued screen and mark it `in_progress` |
| `add-flow` | Register a flow (core or secondary) with its entry route |
| `update-flow` | Set status/report path on a flow, and record each case run |
| `add-screen` | Queue a newly discovered screen with its route |
| `update-screen` | Set status/report path/screenshots/notes on a screen |
| `add-node` | Declare a non-screen diagram node (system step, gate, storage, terminal) |
| `add-edge` | Record one transition you traversed, with its trigger and evidence |
| `render-diagram` | Generate a Mermaid user-flow diagram (`--scope app\|flow\|journey`) and lint the graph |
| `add-finding` | Record an ad slot, paywall, bug, data behaviour, or blocker |
| `set-phase` | Move between phases |
| `render-index` | Regenerate `README.md` from the changelock |

Run `python3 scripts/changelock.py --help` (or `<cmd> --help`) for exact flags.

## Camera fixture script

`scripts/camera_fixture.py` gets a known image into the app's capture path so
camera flows can be run instead of skipped. Read `references/camera-flows.md`
before using it — the routes have different fidelity and the report must say
which one produced each case.

| Command | What it does |
|---|---|
| `check` | Per-target capability report and which route to take |
| `enable-avd-cam` | Switch an AVD's camera on (`hw.camera.back`); needs a cold boot |
| `scene` | Install (or `--restore`) the virtual-scene poster geometry, `--preset fill\|fit` |
| `show` | Swap the emulator's live camera image — no restart, ~1 s per case |
| `fetch` | Download candidate subject photos (Wikimedia Commons) with licence and source recorded |
| `make-fixture` | Promote a candidate to a fixture, or build a test card |
| `barcode` | Generate an EAN-13/UPC-A/QR/Code128 fixture with a known payload |
| `degrade` | Derive a boundary-case variant (blur, rotate, dark, crop, small…) |
| `verify` | Decode a fixture or a camera screenshot — separates a weak scanner from an unreadable fixture |
| `manifest` | List the fixtures with subject, expected answer, source and licence |
| `gallery` | Seed a fixture into the Android gallery or the iOS Simulator library |

Optional extras, only if the app needs them: `pip3 install segno` (QR),
`python-barcode` (Code128 and friends), `zxing-cpp opencv-python-headless`
(`verify`). Everything else runs on Pillow alone.

**Fixtures fetched from the internet must be looked at before use.** `fetch`
saves candidates as `verified: false` for exactly this reason: a downloaded image
that isn't what it claims — the wrong part of the plant, a diagram, a collage —
makes a working app look broken, and that mistake is invisible in the finished
report. Open each candidate, confirm it shows what a user would actually
photograph, then promote it. Barcodes are never downloaded: generate them, so the
expected decode is known exactly.

## Preflight

If the `mobile_*` tools aren't available, the mobile-mcp server isn't connected.
Tell the user and stop — this skill can't do its main job without it. To connect
it, add to `.mcp.json` in the project (or `claude mcp add`):

```json
{
  "mcpServers": {
    "mobile-mcp": {
      "command": "/bin/zsh",
      "args": ["-lic", "npx -y @mobilenext/mobile-mcp@latest"]
    }
  }
}
```

Store research (Phase 1) works without it, so if the user wants to proceed anyway,
offer to do that part and stop before Phase 2.

## Reference files

Read these when the workflow points you at them — they're too detailed to keep in
context the whole time:

- `references/flow-investigation.md` — **read this before you explore anything.**
  How to name the app's core flow, run its happy path end-to-end with real input,
  trace the data lifecycle (persistence, offline, account ownership), build a case
  matrix that covers success as well as failure, and what to do when a list is
  empty. Worked examples for login and for scan/AI-recognition flows
- `references/screen-reading.md` — **read this before the first screen.** The
  six-zone sweep, the six lenses, the mandatory Screen Read and Test Plan formats,
  vision↔accessibility-tree cross-checking, the hypothesis→action→verdict cycle,
  and the evidence rules that keep the report honest
- `references/exploration.md` — the per-screen loop mechanics: route navigation,
  element classification, dedupe by screen signature, scroll capture, recovery
  from stuck states, and how to handle modals, permissions, and interstitials
- `references/camera-flows.md` — **read this when the flow needs the camera.**
  The three routes (emulator virtual scene, photo-library import, physical rig),
  the measured poster presets, live fixture swapping, the fixture set a camera
  flow needs, the camera case matrix, and what each route does *not* prove.
  Driven by `scripts/camera_fixture.py`
- `references/user-flow-diagrams.md` — **read this before the screen loop, not
  after.** How to record transitions as you traverse them, the node and edge
  taxonomy, the three diagrams (app map, per-flow, first-run journey), and the
  accuracy checklist that keeps an arrow from claiming more than you saw
- `references/monetization.md` — ad placement taxonomy, paywall trigger catalog,
  subscription tier extraction, and the analysis templates
- `references/store-research.md` — what to pull from Play Store / App Store /
  landing pages and which signals actually predict what you'll find in the app

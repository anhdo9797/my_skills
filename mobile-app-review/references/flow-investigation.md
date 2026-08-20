# Investigating flows, not just screens

Read this **before** the first detailed screen, and re-read step 5 the moment you
hit an empty list.

## Why this exists

A review can contain twenty tidy screen reports and still be worthless, because it
never answers the only question the user actually has: *what does this app do, does
it work, and what do you get out of it?*

Take a plant scanner. A screenshotter's review says: "Home has a Scan button, a
`3/5 scans left` counter, a bottom banner ad, and a History tab (empty)." All true,
all trivia. What the user needed was:

> Scanning a leaf takes ~4 s, uploads the photo (fails in airplane mode → it's
> server-side), returns species + a health verdict + a confidence % + three care
> tips. The result lands in History and survives a kill/relaunch. Free tier is 3
> scans/day, reset at local midnight; the 4th scan opens a paywall *after* the
> photo is taken, not before. Scanning a human hand returns "Monstera deliciosa,
> 87% confident" — the model has no reject option, which is the app's biggest
> quality problem.

Same app, same session length. The difference is entirely where the effort went.

**Budget more effort on the one core flow than on any five secondary screens.**
Screens are the map; flows are the territory. A screen report tells you what
exists; a flow report tells you what happens, what data moves, and what the app is
actually worth.

## Contents

- [Step 1 — Name the core flow before you explore](#step-1--name-the-core-flow-before-you-explore)
- [Step 2 — Complete the happy path first](#step-2--complete-the-happy-path-first)
- [Step 3 — Trace the data lifecycle](#step-3--trace-the-data-lifecycle)
- [Step 4 — Build the case matrix](#step-4--build-the-case-matrix)
- [Step 5 — An empty list is a task, not a finding](#step-5--an-empty-list-is-a-task-not-a-finding)
- [Step 6 — Write the flow report](#step-6--write-the-flow-report)
- [How flows and screens interleave](#how-flows-and-screens-interleave)

---

## Step 1 — Name the core flow before you explore

Before you tap anything with intent, write down one sentence: **what is this app
for?** Then write the flow that delivers it, as a line:

```
CORE FLOW — scan-plant
Job:     "Point your camera at a plant and learn what it is and whether it's sick"
Trigger: Home → Scan button
Steps:   camera permission → frame subject → capture → processing → result
Output:  species name, health verdict, confidence, care tips
Lands in: History tab, Home "recent" row
```

The store listing (Phase 1) usually hands you this: the headline of the long
description *is* the core flow, and the IAP list tells you where it gets gated.

**The test for "core":** if this flow silently broke, would the app be pointless?
If yes, it's core. Most apps have exactly one core flow and three to six secondary
ones — auth, onboarding, save/history, share/export, upgrade, sync.

Secondary flows still matter, but they're worth exploring *after* the core one,
because a review that nails auth and misses the scanner has its priorities exactly
backwards.

Register the flows in the changelock (`add-flow`) so a resumed session knows which
one is unfinished. `status` will warn you if a core flow is still open — that
warning means the review is not usable yet, no matter how many screens are done.

## Step 2 — Complete the happy path first

Run the flow the way a real, cooperative user would: valid input, permissions
granted, network on, all the way to a real result. **Finish this before you touch
a single error case.**

Two reasons, and both matter:

1. **Errors are unreadable without a baseline.** "Login shows *Invalid
   credentials*" is meaningless until you know a valid login works — otherwise you
   can't distinguish correct rejection from a broken endpoint. The happy path is
   the ruler you measure everything else against.
2. **The happy path is the product.** It's what ~95% of users experience. A review
   that catalogues eight failure modes and never shows what success looks like has
   described the app's edges and skipped its middle.

A happy path counts as done only when you have all of these:

- **Real input**, not a placeholder. A scanner needs a real subject; a search needs
  a query with results; a form needs plausible data. For camera input that subject
  is a prepared fixture image — `references/camera-flows.md`.
- **Every intermediate state screenshotted** — loading, progress bar, interstitial
  ad, permission prompt, success toast. The states between tap and result are where
  the monetization and the perceived-performance tricks live.
- **The result expanded to its full state, not its arrival state.** Results
  routinely land in a bottom sheet peeking a fraction of the screen, or a card
  with truncated text — recognize the affordance (grabber bar, dimmed background,
  "Show more") and act on it before you screenshot. See "Reading affordances, not
  just content" in `references/screen-reading.md` for the signal-to-probe table.
  A peek-state screenshot is not the output; it's a photo of the drawer the
  output is still sitting in.
- **The output recorded verbatim** — every field, number, unit, confidence value,
  and piece of copy. Paraphrasing the result throws away the thing you came for.
- **Rough timing.** "~4 s" vs "~40 s" is a hard product fact and costs you nothing
  to note.
- **Where the output went.** See the next step.

If the happy path can't be completed (needs a physical object, a paid tier, a real
account), say so explicitly and list what you tried — that's a legitimate,
reportable limit. But treat it as a problem to solve first, not a reason to stop:
step 5 is mostly about how to get past exactly this.

## Step 3 — Trace the data lifecycle

This is what separates a teardown from a UI tour. For the core flow — and any
secondary flow that creates or consumes user data — follow the data all the way
through:

| Stage | The question to answer | Cheap way to answer it |
|---|---|---|
| Input | What exactly goes in? Required vs optional, format, validation timing (on type / on blur / on submit) | Type a bad value and watch when it complains |
| Processing | Local or server? How long? Is there a queue/retry? | Airplane mode: still works → on-device. Fails → server-side |
| Output | What comes back, field by field, verbatim? Any confidence/score? | Screenshot + transcribe |
| Persistence | Does it survive kill + relaunch? Airplane mode? | `mobile_terminate_app` → relaunch → look |
| Reuse | Where else does it surface — History, a Home "recent" row, a counter, a badge, a profile stat? | Walk the other screens right after producing data |
| Ownership | Tied to a local store or an account? Does anonymous data migrate on login? | Note whether login is required to see it |
| Deletion | Can the user edit, delete, export, share it? What happens to derived counters? | Look for swipe actions, long-press, an overflow menu |

The airplane-mode probe and the kill-and-relaunch probe are the two highest
value-per-second actions in the entire review: each takes under a minute and each
answers an architectural question no store listing will ever tell you.

A flow report without a data lifecycle section is a flow report that stopped at the
screenshot.

## Step 4 — Build the case matrix

Only now, with a working baseline and the data path mapped, go after variations.
Write them as a matrix before executing, the same way you write a Test Plan for a
screen — deciding the cases in advance is what stops you from wandering.

| # | Case | Kind | Input | Expected | Observed | Evidence | Verdict |
|---|------|------|-------|----------|----------|----------|---------|
| 1 | Valid scan of a healthy leaf | happy | photo of monstera | species + health | … | `03-result.png` | ✅ |
| 2 | Same photo again | variant | identical input | same answer | … | `05-repeat.png` | ⚠️ differs |

**Kinds, in the order you should execute them:**

- **happy** — success. At least one per flow, always first.
- **variant** — another ordinary way a real person does the same thing: a second
  valid input, gallery import instead of live camera, returning user instead of
  first-run, a different account tier. These reveal consistency.
- **error** — what an ordinary person actually gets wrong: wrong password, no
  network, permission denied, empty required field, quota exhausted.
- **boundary** — limits: max length, zero results, the 4th scan when 3 are free,
  the last day of a trial.
- **abuse** — deliberate nonsense: out-of-domain input, 5 000 characters, rapid
  double-tap. Cheap and occasionally spectacular, but genuinely last.

The ordering is the point. A real user hits a wrong password a hundred times more
often than they paste 5 000 characters, so an exotic-error hunt that runs before
the ordinary cases is effort spent on the least likely path. Hunting only for
breakage also produces a distorted report: the user asked what the app *does*, and
a list of things that go wrong is not an answer to that.

**For any lookup, search, or scan flow, "valid input that legitimately comes back
empty" is a mandatory `error` case, not an optional one.** A barcode that scans
cleanly but isn't in the app's database, a search with zero results, a lookup for
an item the app doesn't carry — these are routine, everyday outcomes for a real
user, completely different from the `abuse` row (garbage/out-of-domain input) a
few rows down. Skipping it because the happy-path scan already "worked" leaves
the single most common failure a user of the feature will hit completely
undocumented. Trigger it deliberately (an unknown barcode, a nonsense search
term) and screenshot the result screen — "not found" is a UI state with its own
copy and layout, worth exactly as much evidence as the success state.

The changelock reflects this at the tooling level: `update-flow --status done`
flags (though does not block) a flow whose case matrix has no case besides
`happy`, and any case recorded without `--evidence` gets flagged too — a case row
in a table with no screenshot behind it is exactly the kind of claim the evidence
rules forbid.

Run each case as hypothesis → action → verdict (the cycle in
`screen-reading.md`). Refuted hypotheses are the most valuable rows in the table.

### Worked example — login / auth

| # | Case | Kind | What it tells you |
|---|------|------|-------------------|
| 1 | Sign up fresh, or log in with a valid account | happy | Does auth work at all; what changes in the UI once you're in; what the account unlocks |
| 2 | Kill and relaunch while logged in | variant | Is the session persisted, or does it ask again |
| 3 | Google / Apple / social sign-in | variant | Which providers, what data they request on the consent screen |
| 4 | Data created anonymously, then log in | variant | **Does local data migrate to the account?** Almost nobody tests this and it's always interesting |
| 5 | Wrong password on a real account | error | Error copy, whether it distinguishes wrong-password from unknown-user (a security signal) |
| 6 | Unregistered email | error | Same — and whether it leaks account existence |
| 7 | Malformed email, empty fields | error | Client-side validation, when it fires |
| 8 | Airplane mode | error | Offline handling: clear message, or an infinite spinner |
| 9 | Forgot password | variant | Does the reset flow actually send anything; is it in-app or email |
| 10 | Browse without logging in | state | **What is gated behind auth and what isn't** — often the most useful row in the table |

Note how few of these are about error messages. The deliverable is understanding
what the app does with your identity and your data; error cases are one instrument
for measuring that, not the goal.

**Never destroy state to test:** don't delete a real account, don't log out of an
account the user owns. Use a throwaway account, or mark the case `blocked` and say
why.

### Worked example — a scan / AI recognition flow

| # | Case | Kind | What it tells you |
|---|------|------|-------------------|
| 1 | Clear photo of a known subject | happy | The full output shape: fields, confidence, tips |
| 2 | A second, different known subject | variant | Is the output shape stable; does confidence vary meaningfully |
| 3 | The **same** input twice | variant | Deterministic or not. Two different answers for one input is a headline finding |
| 4 | Gallery import vs live camera | variant | Whether both entry points exist and whether results differ (`references/camera-flows.md` runs both) |
| 5 | A valid scan/lookup that legitimately has no match (unknown barcode, unlisted item) | error | **The most common real-world failure — mandatory, not optional.** What the "not found" screen looks like, verbatim copy, and whether it offers a next step |
| 6 | Out-of-domain subject (a hand, a wall, a photo of a photo) | abuse | **Does the model have a reject option?** A confident wrong answer is a real quality defect worth reporting |
| 7 | Blurry / dark / partial subject | boundary | Quality gating, retry prompts |
| 8 | The scan that exceeds the free quota | boundary | Where exactly the paywall fires — before capture or after, which is a deliberate and revealing choice |
| 9 | Airplane mode | error | On-device vs server-side, and offline messaging |

## Step 5 — An empty list is a task, not a finding

You will open History, Favorites, Notifications, or Saved and find it empty. That
is not a result. **It means you have not produced the data yet.** Writing "History
screen: empty" and moving on is the single clearest signature of a screenshotter
review — you documented the app's cold-start state and called it the feature.

Ways to produce data, in order of preference:

1. **Run the core flow for real.** Best by far: it populates the app *and*
   validates the flow at the same time. One scan gives you a History with an entry,
   an item detail screen, swipe actions, and a Home recent-row — four screens
   unlocked by one action.
2. **Take what the empty state offers.** Good empty states hand you a "Try a
   sample", "Add your first…", or a demo item. Using it is also how you evaluate
   whether the app solves its own cold-start problem.
3. **Create manually** via the `+` / Add / Import affordance.
4. **Feed a fixture into the camera.** A camera flow is not a blocked flow. On
   an Android emulator you can hang your own image in front of the lens and swap
   it per case without a restart; on any target you can seed the photo library and
   use the import path; on a physical device you can display the fixture on the
   host screen. Read `references/camera-flows.md` and run
   `python3 <skill-dir>/scripts/camera_fixture.py check` — it names the route for
   the target you have and catches the AVD that was created with no camera at
   all.
5. **Log in with a test account** that already has data. If the branch clearly
   needs one and you have none, ask the user once — but ask *after* trying the
   options above, not instead of them.
6. **Deep link or demo mode**, if the landing page, store listing, or a `NEW`/
   `Demo` affordance hints at one.
7. **Change device state** when the feature is state-dependent: grant a permission
   you denied, change locale, wait past a cooldown.

Then **document both states**, in this order:

- **Empty** — what does the app do to break the cold start? Illustration, copy,
  a CTA, a sample, or a blank void? This is a genuine UX finding, and it's the
  first thing every new user sees.
- **Populated** — this is where the actual features live: sort, filter, search,
  swipe-to-delete, multi-select, item detail, share, export, sync indicators, ads
  interleaved in the list. None of it is visible when the list is empty, which is
  exactly why an empty-list report reads as complete while covering nothing.

If you genuinely cannot produce data, write what you attempted and what would
unblock it: "History empty; scan requires a physical plant and the gallery import
path is Pro-only — a Pro account or a seeded database would unblock this." That
sentence is useful. "History: empty" is not.

## Step 6 — Write the flow report

Flow reports live alongside screen reports but are organised by flow, because a
flow crosses many screens and no single screen report can hold it:

```
flows/<flow-id>/README.md
screenshots/flows/<flow-id>/NN-*.png
```

Use `assets/flow-report-template.md`. Cross-link both ways: each participating
screen report links to the flow, and the flow report links to the screens.

Record the flow's state with `update-flow` after each case, the same discipline as
screens — a flow half-tested and honestly marked beats a flow claimed complete.

## How flows and screens interleave

Flows are the spine, screens are the ribs. The ordering that works:

1. **Overview pass** — breadth sketch, name the core flow.
2. **Core flow, end to end** — happy path, data lifecycle, then the case matrix.
   This walks you through several screens anyway *and* fills the app with data.
3. **Screen loop** — now every data-dependent screen has something in it, and the
   screen reports are richer for free. This ordering isn't just priority, it's
   causal: doing it the other way round means re-visiting half the screens.
4. **Secondary flows** — auth, upgrade, share, sync — as budget allows.
5. **Remaining screens**, then synthesis.

If the session is going to die early, it should die having finished the core flow
and half the screens, never the reverse.

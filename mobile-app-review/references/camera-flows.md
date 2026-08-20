# Camera flows

Read this when the app's flow needs the camera: a scanner, a QR/barcode reader,
document capture, OCR, plant/food/skin recognition, receipt import, virtual
try-on, AR, KYC/selfie verification, or a "take a photo" step inside a bigger
flow.

**Camera flows are reviewable. Skipping them is not the default.** For a lot of
apps the camera *is* the product, so a review that marks it `blocked` has skipped
the only part the user could not have guessed from the store listing. Everything
below exists to make the flow runnable — on an emulator, on a simulator, and on a
physical device.

## Contents

- [Pick a route](#pick-a-route)
- [Preflight: can this target see anything?](#preflight-can-this-target-see-anything)
- [Route A — Android emulator, virtual scene](#route-a--android-emulator-virtual-scene)
- [Route B — photo library import](#route-b--photo-library-import)
- [Route C — physical device, live capture](#route-c--physical-device-live-capture)
- [Fixtures: what to point the camera at](#fixtures-what-to-point-the-camera-at)
- [Sourcing fixtures from the internet](#sourcing-fixtures-from-the-internet)
- [Barcode and QR fixtures](#barcode-and-qr-fixtures)
- [The camera case matrix](#the-camera-case-matrix)
- [Reporting honestly](#reporting-honestly)

---

## Pick a route

| | Route A: emulator virtual scene | Route B: photo library | Route C: physical rig |
|---|---|---|---|
| Works on | Android emulator | emulator, simulator, real device | real device |
| Exercises | live capture: preview, framing UI, shutter, torch, autofocus | the import path only | everything, for real |
| Fixture control | exact, swappable in ~1 s | exact | approximate, manual |
| Setup cost | one cold boot | none | needs the user's hands once |
| iOS | — | `simctl addmedia` | yes |

**Default: A on Android, B on iOS.** Run B *as well as* A whenever the app offers
both entry points — whether the two paths produce the same result is itself a
finding (different limits, different quality gates, gallery import gated behind
Pro).

Route C only when the app has no gallery path *and* the platform is iOS, or when a
finding depends on real optics (autofocus, low light, torch, motion blur). It
costs one round-trip to the user, so plan the whole fixture set before asking.

## Preflight: can this target see anything?

Run this before you plan the flow — an AVD created without a camera makes every
camera case impossible, and that is a five-second fix, not a blocker:

```bash
python3 <skill-dir>/scripts/camera_fixture.py check
```

It reports, per connected target: emulator vs physical, `hw.camera.back`, whether
live fixture swapping is available, whether the emulator is on software GL (which
makes the virtual scene a blocky mess), any host webcam, and whether a simulator
is booted. It ends with the route to take.

Two failure modes it catches, both common:

- **`hw.camera.back=none`** — the AVD was created with the camera off, so the app
  finds no camera at all and every camera flow dead-ends. Fix:
  ```bash
  python3 <skill-dir>/scripts/camera_fixture.py enable-avd-cam --avd <NAME>
  ```
  then cold-boot the emulator.
- **software GL** (`-gpu swiftshader`/swangle) — the virtual scene renders at a
  fraction of the resolution and the app receives a blocky image that no scanner
  or OCR will read. Relaunch with `-gpu host`. This is the difference between
  "the app's recognition is broken" and "your emulator was rendering mush", and
  reporting the first when the second is true is a serious error.

## Route A — Android emulator, virtual scene

The emulator's back camera can render a 3D room (the "virtual scene") and it can
hang **your image** on the wall of that room. The app's live camera genuinely sees
it: preview, autofocus UI, shutter, and the captured JPEG all carry the fixture.

### One-time setup

The stock poster hangs at an angle on a side wall, so the camera does not see it.
Install the poster geometry that puts it straight in front of the lens:

```bash
python3 <skill-dir>/scripts/camera_fixture.py scene --preset fill   # or --preset fit
```

This rewrites `$ANDROID_SDK/emulator/resources/Toren1BD.posters` (backing up the
original to `Toren1BD.posters.orig`; `--restore` puts it back). Geometry is read
at emulator start, so cold-boot once:

```bash
emulator -avd <NAME> -gpu host -camera-back virtualscene \
  -virtualscene-poster wall=/abs/path/fixture-01.png -no-snapshot-load
```

Presets, both measured on an API 36 portrait AVD with the stock Camera app:

| Preset | Geometry | What you get |
|---|---|---|
| `fill` | `size 2.0 2.6`, `position 0 -0.4 -1.1` | the fixture covers the whole preview, no room visible; roughly the central 75% of the image is in frame, so keep the subject inside the central 60% |
| `fit` | `size 1.2 1.6`, `position 0 0.05 -1.7` | the whole fixture is visible, framed by the room — nothing cropped, subject smaller |

Use `fill` for recognition, OCR and QR (the subject should dominate the frame),
`fit` when the app needs to see the whole document or when you're testing its
edge/crop detection.

Tuning, if your AVD's preview aspect differs: `position` is `x y z` in metres, the
lens sits around `y=0.9` looking down `-z`. Larger `|z|` shrinks the poster,
larger `y` raises it. Change one number, cold-boot, screenshot the preview.

### Per-case: swap the image live

No restart needed between cases:

```bash
python3 <skill-dir>/scripts/camera_fixture.py show /abs/path/fixture-02.png
# wraps: adb emu virtualscene-image wall /abs/path/fixture-02.png
```

The feed changes in about a second. **Screenshot the app's preview after every
swap** — that screenshot is both your framing check and the evidence that this
case ran against this fixture.

### Things that will bite you

- **The front camera is not the virtual scene.** It is a synthetic moving pattern
  (a green blocky scene). Many camera UIs open the front camera first, or
  remember the last one used. If the preview shows green mush, you are on the
  front camera — switch cameras in the app before concluding anything.
- **Permissions are yours to control**, and both directions are test cases:
  ```bash
  adb shell pm grant  <pkg> android.permission.CAMERA   # skip the dialog
  adb shell pm revoke <pkg> android.permission.CAMERA   # test the denied path
  ```
  Revoking usually kills the app process — that's expected, relaunch.
- **The captured still is smaller than a real phone's**: ~960×1280 on the AVD
  measured here. If the app rejects an image as too small or low-quality, that's
  the emulator, not the app — verify on a real device before reporting it.
- **The fixture is a flat poster in a lit room.** Glare, hand shake, skew and
  focus hunting don't exist here. Anything the app does about those is untested
  on this route; say so.
- Screenshots capture the camera preview fine, unless the app sets `FLAG_SECURE`
  (common on KYC/banking screens) — then you get a black frame. Record that
  behaviour rather than fighting it.

### Alternative: pipe a host webcam in

`-camera-back webcam0` makes the emulator use a host camera. Pointed at a real
scene, or at a virtual camera (OBS Virtual Camera and similar) that plays a video
or shows a still, this gives motion and real optics. Check availability first —
`emulator -webcam-list` prints nothing if the host has no camera or macOS has not
granted camera permission to the emulator. Use it when the flow needs *movement*
(video capture, liveness checks, continuous scanning); the virtual scene is
simpler for everything else.

## Route B — photo library import

Most camera features ship a "choose from gallery" twin. It exercises the same
processing, result, persistence and quota machinery — everything after capture —
and it works on every target including the iOS Simulator, which has no camera at
all.

```bash
# Android emulator or physical device
python3 <skill-dir>/scripts/camera_fixture.py gallery /abs/path/fixture-01.png
# iOS Simulator (boot it first)
python3 <skill-dir>/scripts/camera_fixture.py gallery /abs/path/fixture-01.jpg --platform ios
```

Under the hood: `adb push … /sdcard/Pictures/` (modern Android indexes pushed
files automatically; a `MEDIA_SCANNER_SCAN_FILE` broadcast is sent as a fallback,
and the script verifies the file really is in MediaStore), or
`xcrun simctl addmedia booted <file>`. If the Photos app was already open on iOS,
kill and reopen it before picking.

When the app has **no** gallery button, check whether it accepts a shared image
before giving up:

```bash
adb shell dumpsys package <pkg> | grep -B4 -A4 "android.intent.action.SEND"
adb shell am start -a android.intent.action.SEND -t image/jpeg \
  --eu android.intent.extra.STREAM content://media/external/images/media/<id> \
  --grant-read-uri-permission -n <pkg>/<activity>
```

The `<id>` comes from
`adb shell content query --uri content://media/external/images/media --projection _id:_data`.
This reaches the same pipeline through the share entry point.

What Route B does **not** prove: that live capture works, what the capture UI
offers, whether the quota counts captures and imports the same way, or whether
the paywall fires at the same point. Note the entry point you used in the flow
report — a result obtained by import must not be written up as a scan.

## Route C — physical device, live capture

Real optics, real hardware, and the only live-capture route on iOS. Injection is
not possible on a stock device: image injection needs either a cloud device farm
that supports it, or root/Magisk modules on a device you own — out of scope here.
So the fixture is physical.

The rig, which the user sets up **once**:

1. Mount or prop the phone facing the Mac's screen (a phone stand, or leaning
   against a stack of books), 15–25 cm away, screen filling the frame.
2. Keep the device unlocked and awake: `adb shell settings put global stay_on_while_plugged_in 3`.
3. Ask for one confirmation screenshot of the camera preview so you know the
   framing is right before spending cases on it.

Then you drive it: display each fixture full-screen on the host and run the case.

```bash
open -a Preview /abs/path/fixture-01.png   # then ⌘⌃F for full screen
```

Ask for the rig in **one** message, listing every fixture you'll need, right when
you reach the camera flow — not at the end of the session, and not once per case.
If the user declines or isn't there, fall back to Route B and record the camera
cases as `blocked — needs physical rig`.

Two things make Route C less painful: `scrcpy --video-source=camera` shows the
device's live camera feed on the Mac, so you can check aim without touching the
phone; and screen brightness on the host matters — a dim fixture reads as a
low-light case, which is fine as long as it's deliberate.

## Fixtures: what to point the camera at

Generate them before you start, name them `fixture-NN-<what>.png`, and keep them
in the review folder so a resumed session reuses the same inputs:

```bash
python3 <skill-dir>/scripts/camera_fixture.py make-fixture \
  --out reviews/<slug>/fixtures/fixture-01-monstera.png \
  --from ~/Downloads/monstera.jpg --label FIXTURE-01
```

`make-fixture` letterboxes the source into the central safe area of a 3:4 canvas
and stamps a label, so the subject survives the `fill` preset's crop and every
screenshot says which fixture produced it. With no `--from` it draws a test card
(quadrants plus a line ramp) — useful once, to confirm the pipeline and judge how
much detail the app actually receives. The default `--safe 0.6` is sized for the
`fill` preset; with `fit` (nothing is cropped) pass `--safe 0.9` so the subject
isn't needlessly small.

For a *photo* subject you usually want it edge to edge, the way a real capture
would be — `--fit cover --safe 0.95` centre-crops the photo to fill the canvas
instead of letterboxing it, so the app doesn't receive white bands it would never
see in real use. Keep the default `contain` when nothing in the frame may be lost
(a whole document, a full product package).

A camera flow needs a *set*, not one image. The set is what turns the case matrix
into real coverage:

| Fixture | Purpose |
|---|---|
| A canonical, unambiguous subject | the happy path, and the baseline every other case is compared against |
| The same subject again (same file) | determinism: does the app return the same answer twice? |
| A second, different valid subject | is it actually recognising, or returning one confident default? |
| An out-of-domain subject (a hand, a wall, plain text) | does the model have a reject path, or does it confidently answer wrong? |
| A degraded version (blurred, rotated 90°, half cropped, very dark) | quality gates: does the app warn, retry, or silently guess? |
| A QR/barcode or a text block, if the app scans those | correctness on machine-readable input, where right and wrong are unambiguous |
| A blank/white frame | the "nothing here" state, which many apps forget |

Generate degraded variants from the canonical one so the only difference is the
degradation — anything else confounds the comparison; `degrade` does exactly
that. Where the subjects come from is the next section.

## Sourcing fixtures from the internet

You usually don't have a monstera, a Coca-Cola can and a Vietnamese banknote on
your desk. You don't need them: infer what the app expects to see, fetch a real
photo of exactly that, verify it with your own eyes, and promote it to a fixture.

The pipeline, and none of these steps is optional:

1. **Infer the recognition domain** from Phase 1 store research and the app's own
   copy. "Identify 10,000+ plants" → plant photos. "Scan any barcode" → generated
   codes. "Log your meal" → prepared dishes, plated, as a phone would see them.
   Write the subject list before downloading anything: one canonical subject, one
   or two alternatives, one deliberately out-of-domain, plus the degraded variants.
2. **Fetch candidates.**
   ```bash
   python3 <skill-dir>/scripts/camera_fixture.py fetch \
     --subject "Monstera deliciosa leaf" --expected "Monstera deliciosa" \
     --out-dir reviews/<slug>/fixtures --count 3
   ```
   Wikimedia Commons is the default source for good reasons: no API key, stable
   direct URLs, an explicit licence recorded for you, and file titles that *name
   the subject* — which is the ground truth you need. Downloads are saved as
   `raw-*` and recorded in `fixtures/manifest.json` with `verified: false`.
   Commons rate-limits bursts (HTTP 429), so fetch a handful at a time.
3. **Look at every candidate before you use it.** Open the file and check: is this
   really the subject, is there one clear instance of it, is it a photo rather than
   a diagram or a collage, no watermark, and does it look like something a *user*
   would photograph? This is not a formality. Searching Commons for "Monstera
   deliciosa" returns close-ups of the plant's *inflorescence* — botanically
   correct, and useless as a plant-ID fixture, because no user photographs that.
   Adding "leaf" to the query fixed it. A fixture you didn't look at can make a
   working app look broken, and that error is invisible in the report.
4. **Promote what you trust**, which copies the provenance forward and marks it
   verified:
   ```bash
   python3 <skill-dir>/scripts/camera_fixture.py make-fixture \
     --from reviews/<slug>/fixtures/raw-monstera-deliciosa-leaf-01.jpg \
     --out  reviews/<slug>/fixtures/fixture-02-monstera.png --label FIXTURE-02
   ```
5. **Derive the degraded variants from the promoted fixture**, so the only
   difference is the degradation:
   ```bash
   python3 <skill-dir>/scripts/camera_fixture.py degrade \
     reviews/<slug>/fixtures/fixture-02-monstera.png --mode blur \
     --out reviews/<slug>/fixtures/fixture-07-monstera-blur.png
   ```
   Modes: `blur` · `rotate` · `dark` · `lowcontrast` · `invert` · `crop` · `small`.
6. **Check the manifest before you start the case matrix**:
   `camera_fixture.py manifest reviews/<slug>/fixtures`. Anything still marked
   `??` has not been looked at — deal with it now, not after you've written
   conclusions on top of it.

Two rules that keep this honest:

- **You must know the correct answer**, or the case proves nothing. For species,
  dishes and landmarks the Commons title gives it to you. For "how many calories
  is this bowl of phở" or "is this product in the app's database" there *is* no
  external ground truth — then the case tests plausibility and consistency, not
  correctness, and the report must say which.
- **Licence matters because your screenshots ship the image.** Prefer Commons
  (CC/PD) over an arbitrary web image; the manifest records the source URL,
  licence and author so the report can credit it.

## Barcode and QR fixtures

**Never download a barcode image.** A fixture is only useful if you know what the
correct decode is, and a picture of a code found on the web carries an unknown
payload. Generate them instead — then the expected result is exact:

```bash
python3 <skill-dir>/scripts/camera_fixture.py barcode --type ean13 \
  --value 544900000099 --out fixtures/fixture-01-coke.png --label FIXTURE-01
python3 <skill-dir>/scripts/camera_fixture.py barcode --type qr \
  --value "https://example.com/x" --out fixtures/fixture-06-qr.png
```

`ean13` and `upca` are drawn from the standard pattern tables with no
dependencies (a 12-digit value gets its check digit computed; a wrong one is kept
on purpose, with a warning, because that's a test case). `qr` needs
`pip3 install segno`; `code128`, `code39`, `ean8`, `itf` and friends are
delegated to `pip3 install python-barcode`.

The case set for a scanner, with what each one actually answers:

| Fixture | Value | Answers |
|---|---|---|
| Real retail EAN-13 | `5449000000996` (Coca-Cola) | happy path: decode **and** product lookup |
| Same fixture again | same | determinism, caching |
| A second real EAN-13 | | is it looking anything up, or echoing one default |
| Valid checksum, absent from the DB | e.g. `9999999999993` | separates "can't read the code" from "not in the database" — usually the most revealing case in the whole matrix |
| Wrong check digit | `5449000000990` | see the note below |
| QR with a URL | `https://…` | does it open a browser, and does it warn first (a real security question) |
| QR with text / wifi / vCard | | payload-type handling vs dumping raw text |
| `code128` / `code39` | any | symbologies the listing claims but the scanner may not support |
| Degraded variants of the canonical code | `--mode blur/rotate/small/dark` | quality gates and error copy |
| A non-code image (the test card, or a plant fixture) | — | false positives |

**Verify readability before you blame the app.** This is the step that keeps a
barcode review honest: decode the fixture, and decode the *screenshot of the app's
camera preview*. If the code decodes in what the camera sees and the app shows
nothing, that's a finding about the app. If it doesn't decode, it's your framing.

```bash
pip3 install zxing-cpp opencv-python-headless        # once
python3 <skill-dir>/scripts/camera_fixture.py verify fixtures/fixture-01-coke.png \
  --expect 5449000000996
python3 <skill-dir>/scripts/camera_fixture.py show fixtures/fixture-01-coke.png
# screenshot the app's preview, then:
python3 <skill-dir>/scripts/camera_fixture.py verify screenshots/…/01-preview.png \
  --expect 5449000000996
```

Measured on the API 36 AVD with the `fill` preset, decoding the emulator's own
camera preview screenshot — i.e. what any scanner app on that emulator receives:

| Fixture | Decodes from file | Decodes through the emulator camera |
|---|---|---|
| Canonical EAN-13 | yes | **yes** |
| QR | yes | **yes** |
| `--mode dark` (22% brightness) | yes | yes — darkness alone is a weak degradation |
| `--mode small` (30% size) | yes | yes |
| `--mode rotate` 90° | yes | **no** — the `fill` preset crops the code's ends; use `--preset fit` for rotated or long codes |
| `--mode blur` | no | no — this is your reliable "unreadable" case |
| Wrong check digit | no | no |

Two consequences worth writing down before you run the matrix:

- A **wrong check digit is rejected by the decoder itself**, so that case tests the
  app's *no-code-found* path, not "does the app accept an invalid code". To test
  the database path you need a checksum-valid code that simply isn't in the DB.
- If `dark` and `small` still decode for a reference decoder but the app fails
  them, that *is* a finding: the app's scanner is weaker than the baseline. That
  claim is only available because you measured the baseline.

Barcode-specific things to measure while you're in there: time from code-in-frame
to result, auto-detect vs manual shutter, beep/haptic, whether scanning continues
after a result, multi-scan/batch mode, torch, and — the decisive one — **airplane
mode**: a code that still decodes but yields no product name means the catalogue
lives on a server, which answers "does this app work offline" for real.
`adb logcat | grep -iE "barcode|zxing|mlkit|scandit"` often names the scanning SDK,
which is a good teardown detail.

## The camera case matrix

Add these to the flow's case matrix (`references/flow-investigation.md` step 4).
Kinds as usual: `happy` · `variant` · `error` · `boundary` · `abuse` · `state`.

| # | Case | Kind | What it answers |
|---|---|---|---|
| 1 | Canonical fixture, live capture | happy | the whole pipeline: capture → processing → result shape, and how long it takes |
| 2 | Same fixture again | variant | determinism, and whether results are cached |
| 3 | Second valid fixture | variant | is it recognising, or guessing a default |
| 4 | Gallery import of the same fixture | variant | does the import path exist, is it gated, does it produce the same answer |
| 5 | Camera permission denied | error | the degraded path: clear explanation and a way back, or a dead end |
| 6 | Out-of-domain subject | abuse | reject path vs confident wrong answer — a real quality defect worth reporting |
| 7 | Degraded fixture (blur/rotation/dark) | boundary | quality gates and error copy |
| 8 | Airplane mode during processing | error | on-device vs server-side, and the offline message |
| 9 | The capture that exceeds the free quota | boundary | **where** the paywall fires — before framing, after capture, or after processing. Charging attention before showing the result is a deliberate choice and a headline finding |
| 10 | Leave mid-capture (back out, background the app) | state | is the partial capture kept, discarded, or does it crash |

Case 1 must land before any of the others. And note for each case which route
produced it — cases 1, 5, 7, 10 need Route A or C; case 4 is Route B by
definition.

## Reporting honestly

In the flow report's **Data lifecycle** table, the `Input` row states the route
and the fixture, verbatim:

> Input — live capture, Android emulator virtual scene, `fixture-01-monstera.png`
> (960×1280 as received by the app); gallery import also available and tested
> with the same fixture.

Then, in **Not tested / blocked**, name what the route could not reach — for
Route A that is usually glare, hand shake, autofocus, low light and real sensor
noise. That sentence is what keeps the review trustworthy: the user can tell
exactly how far the camera evidence goes.

Never describe a result obtained by gallery import as a scan, never present the
emulator's still resolution as the app's output quality, and never infer that
recognition "works well" from one fixture — one fixture only proves the pipeline
runs.

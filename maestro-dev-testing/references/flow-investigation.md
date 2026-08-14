# Investigating an Unknown Flow

You can only write a reliable Maestro flow if you actually know two things: **how a
user navigates to the screen under test**, and **what selectors identify the elements
on it** (a `testTag`, the exact visible text, an accessibility label). When a
requirement names a screen deep in the app — "edit the amount of an ingredient on the
recipe detail" — you usually know the *destination* but not the *path* or the
*selectors*. Guessing them produces flows that tap the wrong thing and fail for the
wrong reason, which is worse than no test.

So before authoring, close that gap deliberately. Do **not** invent step text or ids
from imagination. Work the four sources below **in order, cheapest first**, and stop as
soon as you can write each step against a real, verified selector.

## The worked example

> "Test updating the amount of an ingredient." The real path is: open app → skip
> onboarding (if shown) → Recipes tab → open any recipe (detail) → scroll to the
> Ingredients section → edit.

You are asked only about the *edit*. Everything before it is navigation you must
recover from somewhere — that "somewhere" is what this file is about.

## Source 1 — Reuse what the suite already knows (always check first)

The earlier features already encode most navigation. Grep `.maestro/` before anything
else; a reusable subflow is both the fastest answer and the right long-term shape.

- `flows/common/` holds shared entry points. This repo already has
  `launch_clear_state.yaml`, `launch_keep_state.yaml`, and **`open_recipes_tab.yaml`**
  (cold start → skip onboarding → land on the Recipes tab). For the example above, that
  one subflow gives you the entire path up to the recipe list for free — `runFlow` it.
- `flows/features/<other>/*.yaml` show how prior scenarios selected elements on shared
  screens (e.g. `like_01_*` shows the recipe-card heart is matched by accessibility
  label `Bookmark recipe` anchored relative to the recipe title). Copy the *selector
  strategy*, not just the text.
- The per-feature `TESTCASES.md` files record anchor data (seed recipes, known labels,
  toast strings) you can reuse verbatim.

If a needed path segment already exists as a subflow, reuse it. If it exists inline in
several flows but not as a subflow, that's a signal to extract one (see "Promote to a
common subflow").

## Source 2 — Read the app's Compose source for real selectors

When the suite doesn't cover the destination screen, the source code is the ground
truth for selectors. Find the screen's composable under the app's source tree —
typically `app/src/main/java/<package-path>/features/<feature>/presentation/` (grep for
the screen name if the layout differs) — and look for, in selector-priority order:

- `Modifier.testTag("…")` and `semantics { testTag = … }` → the best, locale-proof
  selector (`tapOn: { id: "…" }`).
- `contentDescription = …` on icons/images → becomes Maestro's accessibility-label
  text selector (this is how `Bookmark recipe` works).
- `stringResource(R.string.…)` / literal `Text("…")` → the visible text; resolve the
  resource in `res/values/strings.xml` to the actual on-screen string. Use the values
  folder for the **locale the app actually runs in** (e.g. `values/` for English; if the
  app is pinned to one locale, use that one — selectors must match what's rendered).

If the screen has **no** `testTag`s and only ambiguous text, say so explicitly and
recommend adding a `testTag` rather than shipping a coordinate-based flow that will rot.
Also note when the requirement names a screen or control that **doesn't exist in the
source at all** — that's a real finding (the feature isn't built yet), not something to
paper over with a guessed selector. Surface it and ask.

## Source 3 — Inspect a live screen (Maestro MCP or Studio)

When the source is ambiguous or you want to confirm what actually renders, look at the
running app. This needs a booted emulator/device with the variant installed.

**Maestro MCP (preferred for an agent — structured, no screenshots to eyeball):**
If the `maestro` MCP server is connected, it exposes these tools over stdio:

| Tool | Use it to |
|------|-----------|
| `list_devices` | confirm an emulator/simulator is available |
| `inspect_screen` | get the current screen's view hierarchy as compact JSON — read off ids, text, accessibility labels, bounds |
| `take_screenshot` | capture the screen visually to disambiguate layout |
| `run` | execute an inline-YAML or file flow to drive the app to the next screen, then inspect again |
| `cheat_sheet` | pull Maestro syntax/best-practice reference |

**Token rule (important):** a raw `inspect_screen` / hierarchy dump is ~250k tokens for one
screen, ~95% noise — **never read it straight into context.** Two cheap ways instead:
- Write the dump to a file with a CLI command (its output never enters context), then filter:
  ```bash
  adb exec-out uiautomator dump /dev/tty > /tmp/dump.xml
  python3 scripts/filter_hierarchy.py /tmp/dump.xml   # compact table: label | id | class | flags | bounds
  # or: maestro hierarchy | python3 scripts/filter_hierarchy.py
  ```
- Or delegate to a subagent: "inspect this screen and return the best selector for element X" —
  it reasons over the full hierarchy in its own context and returns only a few lines.

Drive-and-inspect loop: `run` a few steps to advance to the target screen → filtered
`inspect_screen` → read the real selectors → write the next step → repeat. This is the
most reliable way to recover a deep path.

Install it if it isn't connected (tell the user, then):

```bash
claude mcp add maestro -- maestro mcp
```

**Maestro Studio (interactive, human-driven fallback):** `maestro studio` opens a
visual inspector mirroring the device; click an element to get its selector. Point the
user here if the MCP isn't available and you can't read the selector from source.

If no device/MCP is available at all, don't block: author the flow from Sources 1–2,
mark each unverified selector with a `# TODO: verify selector` comment, and tell the
user which steps need a live check before the suite can be trusted.

## Source 4 — Ask the user (when the path is genuinely undiscoverable)

If reuse, source, and inspection still leave a gap — an undocumented gesture, a backend
precondition (seed data, a logged-in account), a screen reachable only under a flag —
ask a **specific** question, not "how does this work?". Ask it in the user's language
(see SKILL.md's language rule); the English phrasings below are just illustrative. Good
asks:

- "I can get to the recipe detail, but I don't see an amount/edit control for
  ingredients in `RecipeDetailScreen.kt`. Is this feature built yet, or can you point me
  to the screen/PRD?"
- "Which recipe should the flow open — is there stable seed data in the `dev` flavor I
  can anchor on, like the `Easy Homemade Pizza Dough` the favorite flows use?"

Cite what you already found so the user only fills the actual gap. If the requirement
came from a document, ask them to paste the relevant section rather than re-describe it.

## Promote a recovered path to a common subflow

Once you've recovered a multi-step navigation, don't bury it inside one feature flow —
extract it to `flows/common/<navigate_to_x>.yaml` and `runFlow` it, exactly like
`open_recipes_tab.yaml`. The next feature that needs the same path then starts from
Source 1 instead of re-investigating. Keep the brittle-step comments (e.g. "tapped by
text because the tab has no testTag — replace with `id` once added") so the fragility
travels with the subflow.

## Definition of done for investigation

Before you write a flow, you should be able to state, for every step: the selector you
will use **and** where it came from (reused subflow X / `testTag` in file Y /
`inspect_screen` / confirmed by the user). Any step you can't source is either a
`# TODO: verify` or a question for the user — never a guess presented as fact.

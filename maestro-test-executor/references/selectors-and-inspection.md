# Selectors & Live Inspection

How to find reliable element selectors without burning tokens. Read this whenever you need a selector you don't already have.

## Token rule (non-negotiable)

A raw view-hierarchy dump from `inspect_screen` is ~250k tokens for a single screen — ~95% of it is noise. **Never read a raw hierarchy dump into the main context.** Route it through `scripts/filter_hierarchy.py` or delegate the inspection to a subagent. The same discipline applies to screenshots and command logs: keep large artifacts out of the main context.

## The cheap-to-expensive order

Selectors are the heart of every flow, but learning them is where this skill burns the most tokens. Follow this order — each step is cheaper than the next, so only fall through when the one above can't answer.

1. **Existing YAML flows** (≈ free). Selectors here are already proven against the running app. Scan them first (Phase 2) and reuse aggressively.
2. **Selector catalog** (≈ free). Once you learn a screen's selectors, persist them to `.maestro/<app-id>/selectors.md` (see below) and read that file on later test cases instead of inspecting again.
3. **Supporting documents / Figma** (cheap). Labels and screen names clarify what to target without touching the device.
4. **Live inspection — via the filter script** (cheap). When you genuinely need the live UI, get a compact table, never the raw dump.
5. **Live inspection — via a subagent** (cheap to the main context). For messy screens where you need full reasoning over the hierarchy.

## Live inspection without the 250k-token dump

The raw hierarchy must never enter the main context. Two safe ways to read it:

**Option A — filter script (default).** Write the dump to a file with a CLI command (its output never enters context), then filter it:

```bash
# Android — uiautomator dump (tiny, token-free)
adb exec-out uiautomator dump /dev/tty > /tmp/dump.xml
python3 scripts/filter_hierarchy.py /tmp/dump.xml

# Or pipe Maestro's hierarchy straight through the filter
maestro hierarchy | python3 scripts/filter_hierarchy.py
```

The script keeps only interactable / assertable nodes and prints a compact table (`label | id | class | flags | bounds`) — typically ~1–5k tokens instead of ~250k. Read that table, pick the selector.

**Option B — subagent (for complex screens).** When a screen is dense or the right selector is ambiguous, delegate: ask a subagent to *inspect the screen and return the best selector for element X*. The subagent reasons over the full hierarchy in its own context and returns only a few lines. No information is lost; the dump never reaches you.

> If you ever call the Maestro MCP `inspect_screen` tool directly, its full JSON lands in your context — that is the expensive path. Prefer Option A or B. Only inspect directly as a last resort, and never re-`Read` a saved hierarchy file (`hierarchy_*.json`) — filter it instead.

## Persist a selector catalog

After inspecting a screen, append what you learned to `.maestro/<app-id>/selectors.md` so future test cases skip re-inspection:

```markdown
## Screen: Recipe Search
| Element | Selector | Source |
|---------|----------|--------|
| Search field | `id: "search_input"` | inspect 2026-06-29 |
| Import button | `text: "Import"` | import-web/flow/trigger.yaml |
```

Check this file before any live inspection.

## Resolving an unknown selector

When a step refers to an element with no known selector:

1. Check existing YAML flows and the selector catalog for elements with similar names
2. If a Figma URL was provided, check label text from the design
3. Inspect the live screen via the cheap path above (filter script or subagent, never the raw dump), then record the result in the selector catalog
4. Fall back to a regex selector: `text: "(?i)edit"` (case-insensitive)
5. Ask the user if still uncertain — never guess

## Selector priority

Choose in this order (most reliable → least):

1. Proven selector from existing flows
2. `id` from live view hierarchy (Maestro MCP)
3. `testId` (explicitly set for testing)
4. `text` — exact visible label
5. `text` with regex — flexible matching
6. Index-based — last resort, fragile

## What NOT to read

**Never** read app source files — Kotlin, Swift, Java, Dart, or any compiled/configuration code. This skill is for non-technical testers and must work without source access. Selectors must come from:

- Existing YAML flows (primary, most reliable)
- The selector catalog (`.maestro/<app-id>/selectors.md`)
- Live inspection via the **filtered** path or a subagent (never the raw `inspect_screen` dump)
- Supporting documents or Figma designs (labels, screen names)
- User clarification when still uncertain

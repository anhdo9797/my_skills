---
name: review-bitbucket-pr
description: Review a Bitbucket pull request from its URL — fetch the diff, validate every finding against the repository's own rules and reachable code paths, post evidence-backed inline comments, and return a severity summary with a merge recommendation. Works on any Bitbucket Cloud or Server repository in any language by deriving each project's conventions from the repository itself. Use whenever the user asks to review, inspect, check, comment on, or dry-run a pull request, or supplies a Bitbucket PR URL, even when they do not explicitly ask for comments to be posted. Do not use for implementing fixes, or for GitHub/GitLab reviews.
compatibility: Live review needs a Bitbucket MCP connector that can read pull requests, diffs, comments and repository files, and create inline comments. Dry-run review works from a local diff, patch, or fixture with no connector at all. Local repository access is optional and strictly read-only.
---

# Review a Bitbucket Pull Request

Review exactly the pull request the user pointed at, comment only where a finding is backed by evidence, and return a concise verdict. Never approve, merge, decline, edit code, or change PR state — the recommendation you return is advice for a human, and taking the action yourself would remove their decision.

## Required reading

Read [references/review-contract.md](references/review-contract.md) before reviewing. It owns the evidence threshold, quality gates, severity model, comment template, deduplication semantics, and the result format. This file owns the workflow around it; when the two seem to overlap, the contract wins on *what counts as a finding* and this file wins on *how to run the review*.

Then load exactly one stack profile (step 4). Profiles live in `references/stacks/`.

## Two modes

Pick the mode from what the user gave you, and say which one you are in when you report:

- **Live review** — the default when a Bitbucket URL and a working connector are both present. You fetch the PR and post real inline comments.
- **Dry run** — use when the user says "dry run", "don't post", "preview", "just tell me", when they hand you a local diff, patch file, or fixture instead of a URL, or when no connector is reachable but a diff is. You run the identical review pipeline and render the comments you *would* post, clearly labelled as unposted. Never write anything to Bitbucket in this mode.

Dry run exists because a preview is genuinely useful before a review lands in front of a team, and because it lets the review logic be tested without a live PR. It changes the output channel only — the evidence bar, the gates, and the severity rules are exactly the same.

Treat a request containing a Bitbucket PR URL as authorization to post in live mode without a separate confirmation round; the user asking for a review is the confirmation.

## Input contract

Accept a Bitbucket Cloud or Server pull request URL, or a local diff/patch/fixture. Optional extras: a PRD, ticket, acceptance criteria, or a requested focus area.

Parse the URL with the bundled script rather than by eye — Cloud and Server have different URL shapes, and hand-parsing is where a GitHub URL quietly becomes a fake Bitbucket review:

```bash
python scripts/parse_pr_url.py "<url>"
```

It prints JSON with `kind`, `host`, `workspace`/`project`, `repo`, and `pr_id`, or exits 2 with a reason. On exit 2, tell the user which host they gave and stop — do not reinterpret a GitHub or GitLab URL as Bitbucket.

Treat a supplied business document as authoritative only when you can tell it actually describes this PR. A PRD for a different ticket is worse than no PRD, because it manufactures confident wrong findings.

Comments and the result are written in **Vietnamese** by default, since that is the reviewing team's language. Honour an explicit request for another language.

## Review workflow

### 1. Establish the source of truth

Identify which operations you actually have: PR metadata, commits, changed files, diff hunks, existing comments, pipeline status, repository file reads, and inline comment creation.

Stop before reviewing when the authoritative source cannot support evidence-based work:

- Live mode: the connector is missing, or lacks read or comment permission.
- The URL resolves to zero or more than one PR.
- The complete changed-file list or diff cannot be retrieved.
- The source and destination revisions cannot be identified.

Report the missing capability and the smallest action that would unblock you. A review inferred from file names, commit messages, or a truncated diff looks the same as a real one to the reader, which is exactly why it is not acceptable.

In dry run the fixture or patch *is* the authoritative source, so apply the same checks to it: no diff, no head revision, or a truncated file list means stop the same way.

### 2. Fetch a stable snapshot

Capture and hold: title, description, author, source and destination branches, head commit, commits, changed files, complete diff hunks, existing comments, and build/pipeline status where available.

If the head moves while you work, refresh the diff and the comment list, throw away stale line anchors, and re-validate each finding against the new head before posting. Posting to a line that has since changed puts the comment on unrelated code.

### 3. Load project context, in priority order

Read the smallest ranges that answer a specific question. Reviewing is cheap to over-read and expensive to over-read *badly* — a wide sweep produces generic findings, while a targeted read of the one caller that matters produces a provable one.

1. Confirmed PRD, ticket, or acceptance criteria for this PR.
2. `AGENTS.md`, `CLAUDE.md`, or the nearest scoped instruction file.
3. A repository-local review checklist or review skill, if the repo ships one (look under `.claude/skills/`, `docs/`, or links from the instruction files).
4. Architecture, contributing, lint, static-analysis, and test configuration.
5. Established implementations in the same feature or layer — the nearest neighbour is usually a better style authority than any general rule.
6. General best practice for the language, as the last resort.

The Bitbucket snapshot is the source of truth. Use a local checkout only after confirming it is the same repository and that the revision you inspect is relevant, and never switch branches or touch the working tree — the user may have work in progress there.

If a code-intelligence tool (GitNexus or similar) is available and indexed for the matching checkout, use it to find affected consumers and execution flows; otherwise use narrow repository search. Having the tool is not itself evidence — only what it returns is.

Never read environment files, credentials, tokens, secrets, databases, private keys, or certificates. If a finding seems to require one, describe what you would need instead of opening it.

### 4. Select a stack profile

Detect the stack from the changed paths and the repository manifest (`pubspec.yaml`, `package.json`, `go.mod`, `build.gradle`, `pyproject.toml`, …), then read the matching profile:

- Flutter / Dart → [references/stacks/flutter-dart.md](references/stacks/flutter-dart.md)
- Anything else, or a mixed diff whose main risk sits outside a known profile → [references/stacks/deriving-a-profile.md](references/stacks/deriving-a-profile.md)

A profile supplies the concrete detectors for that ecosystem: what a user-facing string looks like, what the localization mechanism is, where lifecycle bugs hide, which files are generated. The universal gates in the contract stay the same across every stack; only the detectors change. When the diff spans two stacks, read both profiles but review each file under its own.

### 5. Review behaviour before style

Read every changed hunk, plus enough surrounding code to prove or disprove each candidate issue. When a changed symbol can affect behaviour outside its file, follow it to its direct callers.

Run the contract's three coverage gates — **user-facing copy**, **complexity**, and **compatibility** — against every changed hunk they apply to, using your stack profile's detectors. Keep a running note in your working context, one row per changed hunk, recording which gates applied and what each returned. This is not bureaucracy: without it, hunk 9 of 14 silently gets skipped because hunk 8 looked similar, and a skipped hunk is indistinguishable in the final report from a clean one.

For each candidate finding, establish all of:

- the invariant or confirmed requirement it violates;
- a concrete trigger, or a path that actually reaches it;
- the impact on a user or on the system;
- whether some other layer already handles the case;
- the smallest correction that fits the current architecture;
- whether a missing regression test leaves the defect unprotected.

If any of those is missing, you have a suspicion rather than a finding. Discard speculation and personal preference. When business behaviour is genuinely ambiguous, raise a `Question` — but only when the missing answer would change the verdict.

**Large pull requests.** "Every hunk" stops being achievable somewhere past a few hundred changed lines. When the diff is larger than you can review with real evidence, order the hunks by risk — public API and data-model changes, then async and state handling, then security-relevant paths, then everything else — review as far down that order as your budget allows, and state the achieved coverage plainly in the result. An honest "reviewed 40 of 120 files, prioritised by risk" is useful; an implied full review that was not performed is not.

### 6. Deduplicate and anchor

Group findings by root cause and prefer one representative comment that names the other affected locations. Ten copies of the same note read as noise and get dismissed together.

Before posting, refresh the existing comments and compare by meaning, not wording. Skip anything an unresolved existing comment already covers. Reply to an existing thread only when your evidence materially extends it and the connector supports replies.

Anchor each comment to a line that is actually changed at the current head. If no valid inline anchor exists, post one general PR comment carrying the exact `path:line`. Never park a finding on an unrelated changed line just to make it inline — the reader will act on the wrong code.

### 7. Post, or render

**Live mode:** post the validated comments in the contract's format, without asking again. After each write, record the connector's response including comment ID or URL. If one write fails, continue with the independent comments, then report the failed location and the error. Never report a comment as posted without a successful response — a review that overstates what it did is worse than one that admits a gap.

**Dry run:** render the same comments in the same format under a heading that makes their unposted status unmistakable, with the `path:line` each would target.

### 8. Return the result

Use the exact result structure from the contract, in Vietnamese. Include every posted comment and every failed attempt, or in dry run every proposed comment.

Choose the recommendation from the findings you actually posted:

- `Request changes` — at least one Blocker or Major needs correction. Also use it when several Minor findings cluster in one area and together show the change is not finished; say why in the result so the author can see it is a judgement, not a threshold.
- `Need clarification` — an unanswered Question blocks the verdict and there is no Blocker or Major.
- `Approve with suggestions` — only Minor findings and Suggestions remain.
- `Approve` — nothing actionable and no blocking ambiguity.

A single Minor is deliberately not enough to request changes: blocking a PR on a maintainability nit trains authors to ignore the whole review.

State the applicable copy/localization outcome exactly once, as the contract specifies. This is a recommendation in text only — do not execute an approve action.

## Read-only verification

Run a check only when it materially validates a finding you are about to post. Use the repository's own commands (for Flutter and Dart projects here, that means `fvm flutter` / `fvm dart`). Prefer one focused test over a full analysis pass. Do not generate files, update dependencies, or write to the working tree.

Report command, outcome, and the relevant failure line, briefly. A red pipeline is a lead to investigate, not automatically a code-review finding — it may predate the PR.

## Extending to a new stack

When you repeatedly review a stack that has no profile, write one: copy the shape of `references/stacks/flutter-dart.md`, fill in that ecosystem's detectors, and add it to the list in step 4. `deriving-a-profile.md` explains how to build the detector list from a repository you have not seen before, and is also the correct fallback for a one-off review.

---
name: distribute
description: Build the full mobile release pipeline — Fastlane build and upload lanes, CircleCI jobs, a Notion release page with Feature/Bug/Backlog sections, and a Discord announcement that mentions the assigned members. Use this whenever the user wants to set up CI/CD for a mobile app, add or fix release-note automation, wire an existing build lane to Notion or Discord, add TestFlight, Firebase App Distribution, Play Store, or Shorebird distribution, configure release secrets for CI, diagnose a failing release notification, or reuse the same flow in another iOS, Android, or Flutter project — even when they only say "dựng CI/CD", "set up release automation", or "gửi thông báo release".
---

# Distribute

Set up the release pipeline end to end: **Fastlane → CircleCI → Notion →
Discord**. Each layer owns one thing, and that separation is what makes the flow
debuggable:

```text
CircleCI   prepares the machine and injects secrets
Fastlane   builds, uploads, and owns all release metadata
Notion     receives the release page and returns its URL plus assignees
Discord    announces the release and mentions the right people
```

The most common failure mode when adapting this into a project is collapsing
those layers — putting `curl` calls in `config.yml`, or build logic in the Bash
scripts. Keep the boundary and a broken release is one layer to inspect.

## Start from the matching example

Both examples are complete and worked end to end. Read the relevant one before
writing any config — the details that go wrong here are paths and ordering, and
those only become visible in a full example.

| Situation | Example |
| --- | --- |
| Nothing exists yet | [examples/flutter-circleci-firebase/](examples/flutter-circleci-firebase/) — Fastlane lanes, CircleCI jobs, base64 secret injection, Notion, Discord |
| Fastlane already builds and uploads | [examples/add-notifications-to-existing-fastlane/](examples/add-notifications-to-existing-fastlane/) — a before/after Fastfile pair |

Trim them to the project. An unused iOS platform block in an Android-only repo
is noise that will rot.

## Scope first

Ask, or infer from the repository, before writing anything:

1. Which platforms ship — iOS, Android, or both.
2. Which distribution channel each uses — TestFlight, Firebase App
   Distribution, Play Store, Shorebird.
3. Whether Fastlane and CI config already exist.
4. Which layers the user wants now. "Dựng CI/CD" usually means all four; "add
   Discord notifications" means only the last two.

Build only what was asked for. Attaching notifications to every lane in a
repository because they happen to coexist is how a team ends up with four
Discord messages per release.

## Workflow

1. **Inspect.** Read the project's `Fastfile`, lanes, `Gemfile`, release-note
   file, `.circleci/config.yml`, and runner scripts. Never read `.env*`, key,
   certificate, or credential files.

2. **Install the scripts.** Copy both files from `assets/fastlane/` into the
   project's `fastlane/` directory, preserving executable permissions:
   `publish_notion_release.sh` and `send_discord_release_notification.sh`.

3. **Wire Fastlane.** Read
   [fastlane-integration.md](references/fastlane-integration.md). With no
   Fastlane in the project, start from the greenfield example's
   `fastlane/Fastfile` and trim it to the platforms that ship. With Fastlane already present, keep every
   existing build and upload step and add only the notification call after the
   upload succeeds. Run the repository's impact analysis before editing existing
   helpers or lanes.

4. **Find where env lives.** Read
   [env-layouts.md](references/env-layouts.md) and run its detection commands
   before touching CI. Some projects load env from `fastlane/.env.<flavor>`,
   others from a root `.env.<flavor>`, a `config/` directory, or a
   `--dart-define-from-file` JSON. Only the Fastlane layout reaches Fastlane for
   free; the rest must be exported into the job environment explicitly. Decoding
   a secret to the wrong path is the most common way this pipeline fails — the
   job stays green through the decode step and dies twenty minutes later on a
   missing variable.

5. **Wire CircleCI.** Read
   [circleci-integration.md](references/circleci-integration.md) and start from
   the example's `circleci/config.yml`. Secrets travel as one base64 CI variable
   per file, decoded back to the project's own paths through the job's
   `SECRET_FILES` mapping. Jobs prepare the machine and call
   `bundle exec fastlane <platform> <lane> --env <flavor>`; nothing else.

6. **Configure secrets.** Read
   [environment-configuration.md](references/environment-configuration.md) and
   walk the user through the Notion integration, the Discord webhook, the
   assignee map, and the CI variables. Use the example's
   `fastlane/env.prod.example` as the checklist. Provide names and fake example
   values only — never create, read, or print a real `.env` file.

7. **Set up release notes.** Read
   [release-notes-format.md](references/release-notes-format.md).
   `release_notes.txt` holds three optional sections — Feature, Bug, Backlog —
   and `assets/release_notes.example.txt` shows the shape.

8. **Validate.** Read [validation.md](references/validation.md) and run
   `bash scripts/run_mock_tests.sh fastlane`. It exercises Notion and Discord
   against mocks, including the empty-section and backlog cases. Request
   explicit authorization before any live Notion or Discord request.

9. **Document.** Update the project's own setup documentation when the
   integration changes required environment variables or release commands, and
   hand the user a table of every CI variable to create with the path it lands
   on. That table is the part they cannot derive from reading the config.

## Release notes: Feature, Bug, Backlog

```text
🧩 Features:
- Task title as it appears in Notion

🐞 Bug Fixed:
- Android New [BUG 10] - Crash when opening the camera

📌 Backlog:
- Task deferred to the next build
```

A build that already shipped is worth recording even when its notes are untidy,
so the parser degrades rather than failing:

- An empty section, a missing section, or a placeholder bullet (`- N/A`,
  `- None`, `- Không có`) is skipped, and no empty heading reaches Notion.
- A placeholder is never looked up in Notion, so it cannot report a missing
  task.
- An unknown heading and its bullets are copied verbatim into an **Other notes**
  section instead of aborting.
- With no recognizable content at all, the release page is still created with
  build information.

Every degraded case logs a reason to stderr, which Fastlane surfaces in the job
log. Only a missing release-note file, missing configuration, invalid release
metadata, or a failed page creation is fatal.

Backlog entries appear on the Notion page and, when present, as a `📌 Backlog`
field on the Discord embed. Their owners are deliberately left out of the
mention list: the message asks people to verify the build that just shipped, and
backlog work is not in it.

## Invariants

- Keep the two Bash assets unchanged unless the user requests different
  notification behavior. If adaptation is necessary, modify the project copy —
  not this skill's asset, unless the improvement should become the shared
  default.
- Never log webhook URLs, tokens, or environment contents. Decode secrets in
  CI; never echo a decoded value, and never generate the base64 of a real
  secret file.
- Decode every secret to the path the project already reads it from. Do not
  relocate a project's env layout to match an example.
- Fastlane is the single metadata boundary: platform from the active lane,
  environment from Fastlane's selected dotenv, version and build from the
  completed build or a native Fastlane action.
- Notion runs first; Discord consumes its `release_page_url`, `assignees`, and
  `backlog` output verbatim. Never re-derive them from the release-note file.
- Keep Notion requests 400–500 ms apart and retain bounded retry behavior.
- Resolve assignees from an ordered list of Notion people-property names, using
  only the first matching property per page.
- Preserve an unmapped assignee's original name; never convert it to an
  unassigned label. Restrict Discord `allowed_mentions` to mapped user IDs.
- Query at most two task candidates. Missing, ambiguous, malformed, or failed
  lookups stay as plain release-note text without a task URL.
- Always provide a notification-only lane per platform so the flow can be
  re-run without rebuilding.
- Keep iOS, Android, TestFlight, Firebase, Shorebird, and other distribution
  variants separate unless the user explicitly requests a shared flow.

## Files

| Path | Purpose |
| --- | --- |
| `examples/flutter-circleci-firebase/` | Complete worked pipeline; start here for a greenfield setup |
| `examples/add-notifications-to-existing-fastlane/` | Before/after Fastfile for an existing pipeline |
| `assets/fastlane/publish_notion_release.sh` | Copy as-is into `fastlane/` |
| `assets/fastlane/send_discord_release_notification.sh` | Copy as-is into `fastlane/` |
| `assets/release_notes.example.txt` | Release-note shape |
| `scripts/run_mock_tests.sh` | Mocked Notion/Discord validation suite |

Files under `assets/` are copy sources, not files to execute from the skill
directory. Verify copied Bash scripts with `cmp` or SHA-256 before modifying
them.

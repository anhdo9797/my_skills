---
name: distribute
description: Set up or adapt mobile release distribution notifications with Fastlane, Notion release pages, Discord webhooks, assignee mentions, and CI environment configuration. Use when adding release-note automation, moving notification ownership into Fastlane, connecting an existing build lane to Notion and Discord, configuring notification-only lanes, diagnosing this release flow, or reusing the same scripts in another iOS, Android, or Flutter project.
---

# Distribute

Build around each project's existing Fastlane design. Never generate a universal
Fastfile or replace a working build/upload flow.

## Workflow

1. Inspect the target repository's Fastfile, distribution lanes, release-note
   format, runner scripts, and CI configuration. Do not read `.env*`, key,
   certificate, token, or credential files.
2. Read [fastlane-integration.md](references/fastlane-integration.md) before
   changing Fastlane. Run the repository's required impact analysis before
   editing existing helpers, methods, or lanes.
3. Copy both files from `assets/fastlane/` into the target project's
   `fastlane/` directory and preserve executable permissions:
   - `publish_notion_release.sh`
   - `send_discord_release_notification.sh`
4. Keep the existing build and upload steps unchanged. Add notification delivery
   only after they succeed. Integrate only the requested platform and
   distribution variant.
5. Make Fastlane the single metadata boundary. Derive platform from the active
   lane, environment from Fastlane's selected environment, and version/build
   from the completed build or platform-native Fastlane actions.
6. Call Notion first. Parse its JSON stdout, then pass `release_page_url` and
   unique `assignees` to Discord. Keep stderr for operational logs.
7. Read
   [environment-configuration.md](references/environment-configuration.md) to
   guide the user through identifiers, secrets, local Fastlane configuration,
   and CI variables. Use examples without real secret values.
8. Read [validation.md](references/validation.md), run all applicable checks
   with mocked HTTP calls, and request explicit authorization before a live
   Notion or Discord request.
9. Update the target project's existing setup documentation when the integration
   changes required environment variables or release commands.

## Invariants

- Keep the two copied Bash assets unchanged unless the user requests different
  notification behavior. If adaptation is necessary, modify the project copy,
  not this skill asset, unless the improvement should become the shared default.
- Never log webhook URLs, tokens, or environment contents.
- Keep Notion requests 400–500 ms apart and retain bounded retry behavior.
- Resolve assignees from an ordered list of Notion people-property names and
  use only the first matching property for each page.
- Preserve an unmapped assignee's original name. Never convert it to an
  unassigned label.
- Restrict Discord `allowed_mentions` to mapped user IDs.
- Query at most two task candidates. Leave missing, ambiguous, malformed, or
  failed task lookups as plain release-note text without a task URL.
- Provide a notification-only lane so the flow can be tested without rebuilding.
- Keep iOS, Android, TestFlight, Firebase, Shorebird, and other distribution
  variants separate unless the user explicitly requests a shared flow.

## Assets

Treat files in `assets/fastlane/` as copy sources, not files to execute from the
skill directory. Verify copied files with `cmp` or SHA-256 before modifying them.

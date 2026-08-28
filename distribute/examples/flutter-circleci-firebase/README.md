# Example: Flutter + CircleCI + Firebase/TestFlight

A complete release pipeline for a Flutter app that ships Android through
Firebase App Distribution and iOS through TestFlight, with a Notion release page
and a Discord announcement at the end of both.

Read this file top to bottom before copying anything. Step 4 is the one that
changes per project, and getting it wrong is the usual cause of a green CI job
that fails at the Fastlane step.

## Files

| File here | Copy to |
| --- | --- |
| `circleci/config.yml` | `.circleci/config.yml` |
| `fastlane/Fastfile` | `fastlane/Fastfile` |
| `fastlane/Appfile` | `fastlane/Appfile` |
| `fastlane/Pluginfile` | `fastlane/Pluginfile` |
| `fastlane/env.prod.example` | `fastlane/.env.prod.example` (committed, empty values) |
| `Gemfile` | `Gemfile` |
| `release_notes.txt` | `release_notes.txt` |

Plus the two scripts from the skill's `assets/fastlane/`, copied unchanged:

```bash
install -m 0755 <skill>/assets/fastlane/publish_notion_release.sh   fastlane/
install -m 0755 <skill>/assets/fastlane/send_discord_release_notification.sh fastlane/
```

## Step 1 — Fill in the local env file

Copy the template, then fill in real values locally. This file never enters git.

```bash
cp fastlane/.env.prod.example fastlane/.env.prod
cp fastlane/.env.prod.example fastlane/.env.dev
```

Ensure `.gitignore` contains:

```gitignore
fastlane/.env
fastlane/.env.*
!fastlane/.env.*.example
```

Confirm nothing leaked before continuing:

```bash
git status --short
git check-ignore -v fastlane/.env.prod
```

## Step 2 — Verify the flow locally

Run the notification-only lane first. It touches Notion and Discord without
building anything, so a misconfigured token costs seconds instead of a full
build.

```bash
bundle install
bundle exec fastlane android publish_current_release_notifications --env prod
```

Before pointing it at the team's real channel, run the skill's mock suite, which
needs no network and no real credentials:

```bash
bash <skill>/scripts/run_mock_tests.sh fastlane
```

## Step 3 — Base64 the secret files into CircleCI

Every file CI cannot get from git becomes one base64 CircleCI variable.

```bash
# macOS
base64 -i fastlane/.env.prod | pbcopy
base64 -i fastlane/.env.dev | pbcopy
base64 -i android/app/google-services.json | pbcopy

# Linux (-w0 keeps it on one line)
base64 -w0 fastlane/.env.prod
```

Paste each into **Project Settings → Environment Variables**:

| CircleCI variable | Source file |
| --- | --- |
| `ENV_PROD_FILE` | `fastlane/.env.prod` |
| `ENV_DEV_FILE` | `fastlane/.env.dev` |
| `GOOGLE_SERVICES_JSON` | `android/app/google-services.json` |
| `ASC_KEY_P8` | App Store Connect `AuthKey_XXXXXXXX.p8` |

One variable per file keeps CI and local runs on the same source of truth.
Declaring twenty individual CircleCI variables instead drifts from the local
dotenv within a release or two, and the drift only surfaces as a failed release.

Re-run the `base64` command and update the variable whenever the local file
changes. Nothing detects that automatically.

## Step 4 — Point the paths at THIS project

This is the step to adapt, not copy. `SECRET_FILES` in each job maps a CI
variable to the path the project reads it from:

```yaml
    environment:
      SECRET_FILES: |
        ENV_DEV_FILE=fastlane/.env.dev
        ENV_PROD_FILE=fastlane/.env.prod
        GOOGLE_SERVICES_JSON=android/app/google-services.json
```

A project that keeps its dotenv at the repository root writes this instead:

```yaml
    environment:
      SECRET_FILES: |
        ENV_DEV_FILE=.env.dev
        ENV_PROD_FILE=.env.prod
```

and changes the load step in `prepare_release_env` to match:

```yaml
      - load_dotenv:
          path: .env.${FLAVOR}
```

`${FLAVOR}` is expanded by the shell at run time, so one entry serves every
flavor.

Read `references/env-layouts.md` for how to detect which layout a repository
uses, and for the other secret files that commonly need the same treatment
(keystore, `key.properties`, `GoogleService-Info.plist`, Play Store key).

## Step 5 — Understand what decode and load each do

Two separate steps, because they solve two different problems:

```text
decode_secret_files   base64 CI variable  ->  file on disk at the project's path
load_dotenv           file on disk        ->  exported variables in $BASH_ENV
```

`decode_secret_files` is always needed. `load_dotenv` is needed when anything
other than Fastlane's own dotenv must see the variables — a `flutter build`
step, a Firebase CLI call, or a project whose env does not live under
`fastlane/`. It shell-quotes every value with `printf %q`, so a value containing
`;` or `$` cannot execute as a command, and it logs key names only.

## Step 6 — Ship

```bash
git switch -c build/first-release
git push -u origin build/first-release
```

`build/*` selects the dev flavor, `release/*` selects prod. Change
`select_flavor` if the team already means something different by those names.

To re-announce a build that already shipped — Discord was down, someone deleted
the message — trigger the pipeline with the `notifications_only` parameter set
to true instead of rebuilding.

## What comes out

`release_notes.txt` in, Notion page and Discord embed out.

```text
🧩 Features:
- Known feature title

🐞 Bug Fixed:
- Android New [BUG 10] - Crash when opening the camera

📌 Backlog:
- Deferred task title
```

The Notion page:

```markdown
## Build information

- **Project:** Example App
- **Platform:** Android
- **Environment:** Production
- **Version:** 1.4.0
- **Build:** 42
- **Published at:** 09:30 27/08/2026

## 🧩 Features

- [Known feature title](https://www.notion.so/…)

## 🐞 Bug Fixed

- [Android New [BUG 10] - Crash when opening the camera](https://www.notion.so/…)

## 📌 Backlog

- Deferred task title
```

The Discord embed carries version, the Notion link, a `📌 Backlog` field when
the release has one, the assignees as mentions, and the action text. Sections
that are empty in the release notes appear nowhere — see
`references/release-notes-format.md`.

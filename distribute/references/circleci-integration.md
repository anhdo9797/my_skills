# CircleCI Integration

## Contents

- [Where the boundary sits](#where-the-boundary-sits)
- [Start from the example](#start-from-the-example)
- [Secret injection](#secret-injection)
- [Decode, then load](#decode-then-load)
- [Job shapes](#job-shapes)
- [Executor and tooling requirements](#executor-and-tooling-requirements)
- [Triggering](#triggering)
- [Validation](#validation)
- [Other CI providers](#other-ci-providers)

## Where the boundary sits

CircleCI prepares a machine and injects secrets. Fastlane does everything else:
build, sign, upload, publish the Notion page, send the Discord message.

```text
CircleCI job
  -> checkout, select flavor, decode dotenv, install toolchain
  -> bundle exec fastlane <platform> <lane> --env <flavor>
       -> build / sign / upload
       -> publish_notion_release.sh
       -> send_discord_release_notification.sh
```

Keeping notification logic out of `config.yml` is what makes a release
reproducible locally: the same `fastlane` command a developer runs is the one CI
runs. A `config.yml` that curls Notion directly cannot be tested without pushing
a branch.

## Start from the example

Copy `examples/flutter-circleci-firebase/circleci/config.yml` to
`.circleci/config.yml`, then cut it down to the platforms the project ships.
Its README walks through the whole setup with the exact commands. Adapt rather
than adopt wholesale:

1. Point every `SECRET_FILES` destination at the path this project reads.
2. Match the Flutter/Xcode/Android image versions to what the project pins.
3. Match branch filters to the team's release branches.
4. Replace lane names with the project's actual lanes.
5. Delete the platform the project does not build.

When `.circleci/config.yml` already exists, add jobs and commands to it. Do not
replace a working pipeline.

## Secret injection

Every file CI cannot get from git travels as one base64 CircleCI variable:

```bash
base64 -i fastlane/.env.prod | pbcopy   # macOS
base64 -w0 fastlane/.env.prod           # Linux
```

Paste the result into Project Settings → Environment Variables. This keeps one
source of truth: the same file works locally with `--env prod` and in CI.
Declaring twenty individual CircleCI variables instead drifts from the local
dotenv within a release or two, and the drift only surfaces as a failed release.

The destination paths are the part that changes per project, so the pipeline
takes them from a per-job `SECRET_FILES` variable — one
`CI_VARIABLE=destination/path` per line — rather than hardcoding them in a
command:

```yaml
    environment:
      SECRET_FILES: |
        ENV_DEV_FILE=fastlane/.env.dev
        ENV_PROD_FILE=fastlane/.env.prod
        GOOGLE_SERVICES_JSON=android/app/google-services.json
        ASC_KEY_P8=fastlane/private_keys/AuthKey.p8
```

Determine those paths from the repository before writing them; see
[env-layouts.md](env-layouts.md) for the detection commands and the common
layouts. Decoding to the wrong path produces a job that stays green through the
decode step and fails much later on a missing variable.

## Decode, then load

Two separate steps, because they solve two different problems:

```text
decode_secret_files   base64 CI variable  ->  file on disk at the project's path
load_dotenv           file on disk        ->  exported variables in $BASH_ENV
```

`decode_secret_files` is always needed. `load_dotenv` is needed whenever
something other than Fastlane's own dotenv must see the variables — a
`flutter build` step, a Firebase CLI call, or any project whose env does not
live under `fastlane/`. Fastlane loads `fastlane/.env`, `fastlane/.env.default`,
and `fastlane/.env.<name>`, and nothing else.

`load_dotenv` takes a path parameter that is still shell-expanded at run time,
so one entry serves every flavor:

```yaml
      - load_dotenv:
          path: fastlane/.env.${FLAVOR}
```

It shell-quotes every value with `printf %q` before appending it to
`$BASH_ENV`, so a value containing `;`, `$`, or a space cannot execute as a
command, and it logs key names only — never values.

Rules that matter here:

- Never echo a decoded file, its size aside, and never run `set -x` in a step
  that touches secrets.
- Never generate the base64 of a real secret file on the user's behalf. Give
  them the command and let them run it.
- Never commit a decoded file; `fastlane/.env*` stays gitignored except the
  `.example` template.
- Use contexts or restricted projects when several repositories share one
  Notion integration token.
- Rotate `NOTION_API_TOKEN` and `DISCORD_WEBHOOK_URL` if a job log ever prints
  them.

## Job shapes

| Job | Purpose | Executor |
| --- | --- | --- |
| `android_distribution` | Build APK/AAB, upload to Firebase App Distribution, notify | Docker `cimg/android` |
| `ios_distribution` | Build IPA, upload to TestFlight, notify | macOS with Xcode |
| `release_notifications` | Re-announce an already-shipped build without rebuilding | Docker `cimg/ruby` |

The third job exists because notification failures and build failures need
different remedies. When Notion or Discord is unreachable, rerunning a 40-minute
build to resend a message is waste; the notification-only lane republishes from
current metadata.

## Executor and tooling requirements

The notification scripts need Bash 3.2+, `curl`, and `jq`. macOS executors ship
`curl` but not `jq`; `cimg/android` and `cimg/ruby` ship neither reliably. The
`install_release_tools` command in the example handles both package managers
and fails loudly rather than letting a release job die mid-notification.

Also required in any job that runs Fastlane: Ruby with Bundler, the project's
`Gemfile.lock`, and the Flutter/Xcode/Android SDK the build needs. Cache
`vendor/bundle` and the Flutter SDK; a cold Fastlane install adds minutes to
every release.

## Triggering

Branch filters keep releases deliberate. The example ships:

- `build/*` → dev flavor
- `release/*` → prod flavor

Match the flavor selection in `select_flavor` to whatever the team already
means by those branch names; do not invent a new convention. For manual
re-announcement, the example exposes a `notifications_only` pipeline parameter
so the notification job can be triggered from the CircleCI UI or API without a
new commit.

## Validation

Before pushing:

```bash
circleci config validate .circleci/config.yml
```

If the CLI is unavailable, say so rather than claiming the config was verified.
Then confirm the referenced lanes exist:

```bash
bundle exec fastlane lanes
```

The first CI run should target a non-production flavor with a real but
low-stakes Discord channel. Ask the user before pointing a job at a production
webhook or the team's real release page.

## Other CI providers

The same boundary transfers directly. GitHub Actions, GitLab CI, Bitrise, and
Codemagic each need only: checkout, restore the dotenv from encrypted storage,
install Ruby/Bundler and the platform toolchain, install `jq`, then run the same
`bundle exec fastlane <platform> <lane> --env <flavor>` command. Nothing in the
Bash scripts is CircleCI-specific.

The `SECRET_FILES` mapping transfers as a job-level env var on any provider.
GitHub Actions has no `$BASH_ENV`, so the equivalent of `load_dotenv` appends to
`$GITHUB_ENV` instead; masked values there also need `::add-mask::` when a value
is ever echoed, which it should not be.

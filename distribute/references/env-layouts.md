# Env Layouts

Where a project keeps its environment file is a project decision, not a
convention this skill gets to impose. Decoding secrets into the wrong path is
the single most common way this pipeline fails: the job goes green through the
decode step, then Fastlane reports a missing variable twenty minutes later, or
worse, builds against stale committed defaults.

Detect the layout first, then map every base64 CI variable onto the paths the
project already reads.

## Contents

- [Detect before deciding](#detect-before-deciding)
- [Common layouts](#common-layouts)
- [Reaching the notification scripts](#reaching-the-notification-scripts)
- [Declaring the mapping in CI](#declaring-the-mapping-in-ci)
- [Non-dotenv secret files](#non-dotenv-secret-files)
- [Report the mapping back](#report-the-mapping-back)

## Detect before deciding

Run these against the target repository. Do not open any file that holds real
values — the goal is to learn *where* env lives and *who reads it*, never what
it contains.

```bash
# 1. Which env paths are ignored? .gitignore names the real layout.
grep -nE '(^|/)\.env|env/|\.properties|keystore|\.p8|google-services|GoogleService' .gitignore

# 2. Which templates are committed? Their location is the intended location.
find . -name '*.env.example' -o -name '.env.sample' -o -name 'env.*.example' \
  -not -path './build/*' -not -path './.git/*'

# 3. Who consumes env at build time?
grep -rnE 'dotenv|Dotenv|flutter_dotenv|--dart-define-from-file|ENVFILE|react-native-config|envied' \
  --include='*.dart' --include='*.yaml' --include='*.gradle' --include='*.kts' \
  --include='*.rb' --include='*.json' --include='*.sh' . | head -30

# 4. Does Fastlane already select an environment?
grep -rn 'ENVIRONMENT\|--env\|Dotenv' fastlane/ 2>/dev/null

# 5. What does the existing CI already decode, if anything?
grep -rn 'base64' .circleci/ .github/ bitrise.yml codemagic.yaml 2>/dev/null
```

Existing CI is the strongest signal available: if the team already decodes
`ENV_PROD_FILE` into some path, reuse that variable name and that path rather
than introducing a parallel scheme.

## Common layouts

| Layout | Typical paths | Loaded by | Fastlane sees it? |
| --- | --- | --- | --- |
| Fastlane dotenv | `fastlane/.env`, `fastlane/.env.dev`, `fastlane/.env.prod` | Fastlane's own dotenv when `--env <name>` is passed | Yes, automatically |
| Root dotenv | `.env`, `.env.prod`, `.env.staging` | App code, `flutter_dotenv`, `react-native-config`, or a shell `source` | **No** |
| Nested config dir | `env/prod.env`, `config/.env.prod` | A project script or build flag | **No** |
| Dart define file | `env/prod.json` via `--dart-define-from-file` | The Flutter build command only | **No** |
| Asset dotenv | `assets/.env` bundled into the app | `flutter_dotenv` at runtime | **No** |

Only the first row is wired to Fastlane for free. Fastlane reads
`fastlane/.env`, `fastlane/.env.default`, and `fastlane/.env.<name>`; nothing
else is loaded just because it exists.

## Reaching the notification scripts

`publish_notion_release.sh` and `send_discord_release_notification.sh` read
their configuration from the **process environment**. Whatever layout the
project uses, the Notion and Discord variables must be in the environment at the
moment Fastlane runs. Three ways to get there, in order of preference:

**1. The project already uses Fastlane dotenv.** Add the Notion and Discord
names to `fastlane/.env.<flavor>` and pass `--env <flavor>`. Nothing else to do.

**2. The project keeps env elsewhere and CI must load it.** Export the file into
the job environment before calling Fastlane. The `load_dotenv` command in
`examples/flutter-circleci-firebase/circleci/config.yml` does this: it parses
`KEY=value` lines, strips surrounding quotes, and appends `export KEY=<quoted>`
to `$BASH_ENV`. Values are shell-quoted with `printf %q`, so a value containing
`;`, `$`, or spaces cannot execute as a command. Only key names are logged.

This is usually the right choice, because build steps outside Fastlane —
`flutter build`, a Gradle task, a Firebase CLI call — typically need the same
variables.

**3. The Fastfile loads the file itself.** When local developers must work
without CI, add an explicit load at the top of the Fastfile:

```ruby
require "dotenv"

# The project keeps its environment at the repository root, so Fastlane's own
# dotenv lookup under fastlane/ never sees it.
Dotenv.load(File.expand_path("../.env.#{ENV.fetch('FLAVOR', 'dev')}", __dir__))
```

Add `gem "dotenv"` to the Gemfile. Prefer this only when the team wants one file
for both local and CI runs; it makes Fastlane's behavior depend on a path
convention that is easy to break during a refactor.

Whichever route applies, never invent a second copy of the Notion or Discord
configuration. One file per environment, one loading mechanism.

## Declaring the mapping in CI

The example pipeline drives decoding from a per-job `SECRET_FILES` variable, one
`CI_VARIABLE=destination/path` per line:

```yaml
    environment:
      SECRET_FILES: |
        ENV_PROD_FILE=fastlane/.env.prod
        GOOGLE_SERVICES_JSON=android/app/google-services.json
```

Root-dotenv project instead:

```yaml
    environment:
      SECRET_FILES: |
        ENV_PROD_FILE=.env.prod
        ENV_DEV_FILE=.env.dev
```

and the matching load step:

```yaml
      - load_dotenv:
          path: .env.${FLAVOR}
```

The path is expanded by the shell at run time, so `${FLAVOR}` resolves to
whatever `select_flavor` chose. Keeping the mapping in one place means the next
person adding a secret edits one list instead of hunting through steps.

## Non-dotenv secret files

The same mechanism carries any file that cannot be committed. Common ones:

| File | Typical destination |
| --- | --- |
| App Store Connect key | `fastlane/private_keys/AuthKey.p8` |
| Android upload keystore | `android/app/release.keystore` |
| Keystore passwords | `android/key.properties` |
| Firebase Android config | `android/app/src/<flavor>/google-services.json` |
| Firebase iOS config | `ios/Runner/<flavor>/GoogleService-Info.plist` |
| Google Play service account | `fastlane/play-store-key.json` |
| iOS export options | `ios/ExportOptions.plist` |

Check the flavor-specific directory names in the project before assuming a path;
`src/prod/` and `src/production/` both exist in the wild.

## Report the mapping back

When the integration is done, tell the user exactly which CI variables to create
and which path each one lands on, as a table. That list is what they act on, and
it is the part they cannot derive from reading the config. Include the command
that produces each value:

```bash
base64 -i fastlane/.env.prod | pbcopy   # macOS
base64 -w0 fastlane/.env.prod           # Linux
```

Never generate the base64 of a real secret file yourself, and never print a
decoded value.

# Fastlane Integration

## Contents

- [Inspect before editing](#inspect-before-editing)
- [Greenfield versus existing Fastlane](#greenfield-versus-existing-fastlane)
- [Preserve the release boundary](#preserve-the-release-boundary)
- [Install the assets](#install-the-assets)
- [Run scripts safely](#run-scripts-safely)
- [Connect Notion to Discord](#connect-notion-to-discord)
- [Resolve release metadata](#resolve-release-metadata)
- [Android lanes](#android-lanes)
- [iOS lanes](#ios-lanes)
- [Shorebird and other variants](#shorebird-and-other-variants)
- [Expose a notification-only lane](#expose-a-notification-only-lane)
- [Keep runner scripts thin](#keep-runner-scripts-thin)

## Inspect before editing

Locate the following before proposing Fastlane changes:

1. Build, signing, upload, and distribution lanes.
2. The step that proves the build/upload succeeded.
3. Existing sources for platform, environment, version, and build number.
4. Existing release-note path and format.
5. Fastlane imports, private lanes, helpers, and lane context usage.
6. Runner scripts and CI commands that invoke Fastlane.

Run the repository's impact-analysis workflow before editing an existing Ruby
helper or lane. Report high-risk results before proceeding. Do not infer that
lane names or project paths match another repository.

## Greenfield versus existing Fastlane

Both paths end at the same boundary, but they start differently:

**No Fastlane yet.** Work from
`examples/flutter-circleci-firebase/`: copy its `fastlane/Fastfile`, `Appfile`,
`Pluginfile`, `Gemfile`, and `fastlane/env.prod.example` (as
`fastlane/.env.<flavor>.example`), then delete every lane the project does not
need and run `bundle install`. The example is a starting point that must be
trimmed, not a file to drop in untouched — an unused iOS platform block in an
Android-only repo is noise that will rot.

**Fastlane already exists.** Keep it. Copy only the two Bash scripts, add the
`run_release_notification_script` and `publish_release_notifications` helpers,
and call `publish_release_notifications` at the end of the existing distribution
lane. `examples/add-notifications-to-existing-fastlane/` shows the complete
before/after pair. Never regenerate a working Fastfile from an example.

## Preserve the release boundary

Keep this sequence:

```text
existing build/sign/upload/distribute
-> normalize release metadata in Fastlane
-> publish Notion release page
-> parse release URL, unique assignees, and backlog
-> send Discord webhook
```

Do not move build logic into either Bash script. A notification failure must say
whether the artifact was already built or uploaded, because the remedy differs:
a failed build is rerun, a failed notification is re-sent from the
notification-only lane.

Integrate one platform and distribution variant at a time. Do not attach the
same notification call to TestFlight, Firebase, Shorebird, iOS, and Android
lanes merely because they coexist in the repository.

## Install the assets

```bash
install -m 0755 \
  .agents/skills/distribute/assets/fastlane/publish_notion_release.sh \
  fastlane/publish_notion_release.sh
install -m 0755 \
  .agents/skills/distribute/assets/fastlane/send_discord_release_notification.sh \
  fastlane/send_discord_release_notification.sh
```

When applying this skill from another repository, use the installed skill's
absolute asset path as the source.

## Run scripts safely

Require these Ruby libraries once:

```ruby
require "json"
require "open3"
require "shellwords"
```

Adapt this helper to local naming conventions:

```ruby
# Runs a Fastlane-owned release script and keeps JSON stdout separate from logs.
def run_release_notification_script(script_name, arguments)
  script_path = File.join(__dir__, script_name)
  UI.user_error!("Release script not found: #{script_path}") unless File.file?(script_path)

  command = ["bash", script_path] + arguments.map(&:to_s)
  UI.command(command.shelljoin)
  stdout, stderr, status = Open3.capture3(*command)
  stderr.each_line do |line|
    UI.command_output(line.strip) unless line.strip.empty?
  end

  return stdout if status.success?

  output = [stdout, stderr].reject(&:empty?).join
  UI.user_error!(
    "Release notification failed with exit status #{status.exitstatus}.\n#{output}"
  )
end
```

Do not use `sh(command)` when stdout must be parsed as JSON; Fastlane formatting
and mixed stderr can make valid JSON unparsable.

## Connect Notion to Discord

Define one shared helper and call it from every distribution lane, so the two
platforms cannot drift apart. The full version is in
`examples/flutter-circleci-firebase/fastlane/Fastfile`; the essential data flow
is:

```ruby
notion_output = run_release_notification_script(
  "publish_notion_release.sh",
  [
    "--input", release_notes_path,
    "--platform", platform,
    "--version", version,
    "--build-number", build_number,
    "--environment", environment
  ]
)

notion_result = JSON.parse(notion_output)
UI.user_error!("Notion publication failed.") unless notion_result["success"] == true

release_page_url = notion_result.fetch("release_page_url")
assignees = notion_result.fetch("assignees", [])
backlog = notion_result.fetch("backlog", [])

run_release_notification_script(
  "send_discord_release_notification.sh",
  [
    "--release-url", release_page_url,
    "--assignees-json", JSON.generate(assignees.uniq),
    "--backlog-json", JSON.generate(backlog),
    "--platform", platform,
    "--version", version,
    "--build-number", build_number,
    "--environment", environment
  ]
)
```

`backlog` arrives ready to forward as `[{"text": …, "url": …}]`. Pass it
through; do not re-read the release-note file in Ruby, or the two renderings
will disagree the first time the note format changes.

Catch `JSON::ParserError` at the lane boundary and report invalid script output.
Do not replace a missing `release_page_url` or `assignees` with guessed values.
See [release-notes-format.md](release-notes-format.md) for the full output
contract and the degraded-input rules.

## Resolve release metadata

Fastlane owns all four values:

| Value | Rule |
| --- | --- |
| Platform | Derive from the active platform/lane; render `iOS` or `Android`. |
| Environment | Derive from Fastlane's selected environment and map it to a display label. |
| Version | Reuse the value produced by the current build lane or a native Fastlane action. |
| Build | Reuse the value produced by the current build lane or a native Fastlane action. |

Fastlane's selected dotenv name is available from:

```ruby
Fastlane::Actions.lane_context[
  Fastlane::Actions::SharedValues::ENVIRONMENT
]
```

Map project aliases such as `prod` or `staging` to display labels in Fastlane.
Do not define `RELEASE_PLATFORM` or `RELEASE_ENVIRONMENT` as duplicate static
configuration.

For Flutter, platform lanes still own the rendered platform. Prefer build
outputs or lane context over independently rereading `pubspec.yaml`, because CI
may override build metadata.

## Where env comes from

The two Bash scripts read their configuration from the process environment.
Whether that environment is populated depends on where the project keeps its env
file, which varies — Fastlane only auto-loads `fastlane/.env`,
`fastlane/.env.default`, and `fastlane/.env.<name>`. A project whose env lives at
the repository root needs either an explicit `Dotenv.load` in the Fastfile or an
export step in CI. Read [env-layouts.md](env-layouts.md) before assuming the
variables will be present.

## Android lanes

Version name and code usually come from Gradle. The example reads
`android/app/build.gradle.kts` for the selected flavor, but check the project
first — many repos compute the version in the Flutter build or a CI step, and
that value must win.

A complete Firebase App Distribution lane:

1. Read the latest release build number
   (`firebase_app_distribution_get_latest_release`), tolerating the failure that
   happens on a first release.
2. `increment_version_code` with the next value.
3. Build the APK/AAB with the flavor's dart-defines.
4. `firebase_app_distribution` with the artifact, tester groups, and release
   notes text.
5. Call the shared notification helper with the Gradle metadata.

Plugins required: `fastlane-plugin-firebase_app_distribution`,
`fastlane-plugin-increment_version_code`.

For Google Play instead of Firebase, replace step 4 with `upload_to_play_store`
and keep everything else — the boundary does not change.

## iOS lanes

Build number is normally derived from TestFlight:

1. Build an App Store Connect API key from `ASC_KEY_ID`, `ASC_ISSUER_ID`, and
   either `ASC_KEY_FILEPATH` locally or `ASC_KEY_CONTENT` in CI.
2. `latest_testflight_build_number` + 1, tolerating first-release failure.
3. `increment_build_number` on the Xcode project.
4. `build_app`, then `upload_to_testflight`.
5. Optionally `upload_symbols_to_crashlytics` with the dSYM from
   `lane_context[SharedValues::DSYM_OUTPUT_PATH]`.
6. Call the shared notification helper with `get_version_number` and
   `get_build_number`.

Manual signing needs the distribution certificate imported into a temporary CI
keychain and the provisioning profile installed. If the project already has that
code, leave it alone: signing is the most fragile part of an iOS pipeline and
the least related to notifications.

## Shorebird and other variants

Shorebird replaces the build command only. `shorebird release ios|android` needs
an explicit `--flutter-version`, and its artifacts land in different paths than a
plain Flutter build, so locate the produced IPA/APK before uploading. Everything
after the upload — metadata, Notion, Discord — is unchanged.

Treat Shorebird, TestFlight, Firebase, and Play Store as separate lanes with
separate notification calls unless the user explicitly asks for a shared flow.

## Expose a notification-only lane

Add a lane per platform that obtains current metadata and invokes the shared
helper without build or upload steps:

```bash
bundle exec fastlane ios publish_current_release_notifications --env prod
bundle exec fastlane android publish_current_release_notifications --env prod
```

This is how the flow gets tested without a 40-minute rebuild, and how a release
is re-announced after a Discord or Notion outage. It is not optional.

## Keep runner scripts thin

App-level shell runners may select an environment, clean artifacts, run builds,
and call Fastlane lanes. Keep Notion lookup, Discord payload construction,
release metadata normalization, and JSON parsing under `fastlane/`.

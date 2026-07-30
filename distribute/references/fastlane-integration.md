# Fastlane Integration

## Contents

- [Inspect before editing](#inspect-before-editing)
- [Preserve the release boundary](#preserve-the-release-boundary)
- [Run scripts safely](#run-scripts-safely)
- [Connect Notion to Discord](#connect-notion-to-discord)
- [Resolve release metadata](#resolve-release-metadata)
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

## Preserve the release boundary

Keep this sequence:

```text
existing build/sign/upload/distribute
-> normalize release metadata in Fastlane
-> publish Notion release page
-> parse release URL and unique assignees
-> send Discord webhook
```

Do not move build logic into either Bash script. A notification failure must say
whether the artifact was already built or uploaded.

Integrate one platform and distribution variant at a time. Do not attach the
same notification call to TestFlight, Firebase, Shorebird, iOS, and Android
lanes merely because they coexist in the repository.

Copy the assets to the target project:

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
  UI.user_error!("Release script not found: #{script_path}") unless File.exist?(script_path)

  command = ["bash", script_path] + arguments.map(&:to_s)
  UI.command(command.shelljoin)
  stdout, stderr, status = Open3.capture3(*command)
  stderr.each_line do |line|
    UI.command_output(line.strip) unless line.strip.empty?
  end

  unless status.success?
    output = [stdout, stderr].reject(&:empty?).join
    UI.user_error!(
      "Release notification failed with exit status #{status.exitstatus}.\n#{output}"
    )
  end

  stdout
end
```

Do not use `sh(command)` when stdout must be parsed as JSON; Fastlane formatting
and mixed stderr can make valid JSON unparsable.

## Connect Notion to Discord

Create a project-appropriate private or public lane with this data flow:

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
assignees_json = JSON.generate(notion_result.fetch("assignees", []))

run_release_notification_script(
  "send_discord_release_notification.sh",
  [
    "--release-url", release_page_url,
    "--assignees-json", assignees_json,
    "--platform", platform,
    "--version", version,
    "--build-number", build_number,
    "--environment", environment
  ]
)
```

Catch `JSON::ParserError` at the lane boundary and report invalid script output.
Do not replace missing `release_page_url` or `assignees` with guessed values.

## Resolve release metadata

Fastlane owns all four values:

| Value | Rule |
| --- | --- |
| Platform | Derive from the active platform/lane; render `iOS` or `Android`. |
| Environment | Derive from Fastlane's selected environment and map it to a display label. |
| Version | Reuse the value produced by the current build lane or a native Fastlane action. |
| Build | Reuse the value produced by the current build lane or a native Fastlane action. |

For iOS, existing projects commonly use `get_version_number` and
`get_build_number` with their own Xcode project and target.

For Android, prefer the version name/code already calculated by the Gradle or
Flutter build lane. If absent, use the project's established Gradle/Fastlane
action; do not parse a hardcoded file path without inspecting the project.

For Flutter, platform lanes still own the rendered platform. Prefer build
outputs or lane context over independently rereading `pubspec.yaml`, because CI
may override build metadata.

Fastlane's selected dotenv name is available from:

```ruby
Fastlane::Actions.lane_context[
  Fastlane::Actions::SharedValues::ENVIRONMENT
]
```

Map project aliases such as `prod` or `staging` to display labels in Fastlane.
Do not define `RELEASE_PLATFORM` or `RELEASE_ENVIRONMENT` as duplicate static
configuration.

## Expose a notification-only lane

Add a lane that obtains current metadata and invokes the shared notification
lane without build/upload steps. Its exact platform block and actions must match
the project.

Example invocation:

```bash
bundle exec fastlane ios publish_current_release_notifications --env prod
```

For Android, expose an equivalent Android lane or require explicit version/build
options when the project has no reliable current-build source.

## Keep runner scripts thin

App-level shell runners may select an environment, clean artifacts, run builds,
and call Fastlane lanes. Keep Notion lookup, Discord payload construction,
release metadata normalization, and JSON parsing under `fastlane/`.

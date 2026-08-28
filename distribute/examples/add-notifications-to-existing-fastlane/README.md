# Example: Add notifications to an existing Fastlane setup

The common case. A project already builds and uploads correctly; it just has no
release page and no Discord message. Nothing about the build changes.

`Fastfile.before.rb` and `Fastfile.after.rb` are the same file either side of
the integration. Diff them to see the whole change:

```bash
diff -u Fastfile.before.rb Fastfile.after.rb
```

## What changes

1. `require "json"`, `"open3"`, `"shellwords"` at the top.
2. Two helpers: `run_release_notification_script` and
   `publish_release_notifications`.
3. One call at the end of the existing lane, after the upload succeeds.
4. A `publish_current_release_notifications` lane so the flow can be re-run
   without rebuilding.

Plus, outside the Fastfile: the two Bash scripts copied into `fastlane/`, the
Notion and Discord variables added to whichever env file the project already
uses, and `release_notes.txt` at the repository root.

## What does not change

The build, the signing, the upload, the lane name, and the CI job that calls it.
If the integration requires editing `gradle(...)` or `build_app(...)`, something
has gone wrong — the notification boundary sits strictly after them.

## Adapting the metadata

`android_get_version_name` and `android_get_version_code` come from the
`fastlane-plugin-versioning_android` plugin and only fit projects that use it.
Use whatever the project already trusts:

| Situation | Source |
| --- | --- |
| The lane computes a build number | Reuse that variable directly |
| Gradle owns the version | Parse `android/app/build.gradle[.kts]` for the selected flavor |
| iOS with an Xcode project | `get_version_number` and `get_build_number` |
| CI overrides the version | Read the CI variable, not the checked-in file |

Never invent a second source of truth for version or build number. When the
release page shows a different build than the one testers received, the whole
notification stops being trusted.

## Verify

```bash
ruby -c fastlane/Fastfile
bundle exec fastlane lanes
bash <skill>/scripts/run_mock_tests.sh fastlane
bundle exec fastlane android publish_current_release_notifications --env prod
```

Run the notification-only lane before wiring anything into CI. It exercises the
whole Notion and Discord path in seconds.

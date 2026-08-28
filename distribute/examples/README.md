# Examples

Worked, copy-ready examples. Read the one matching the project's situation
before writing any config — they exist because the details that go wrong are
paths and ordering, and those only show up in a complete example.

| Example | Use when |
| --- | --- |
| [flutter-circleci-firebase](flutter-circleci-firebase/) | Building the pipeline from nothing: Fastlane lanes, CircleCI jobs, base64 secret injection, Notion, Discord |
| [add-notifications-to-existing-fastlane](add-notifications-to-existing-fastlane/) | Fastlane already builds and uploads; only the Notion page and Discord message are missing |

Both are starting points to trim, not files to drop in unchanged. In particular,
every destination path in the CircleCI `SECRET_FILES` mapping has to be pointed
at the path the target project actually reads — see
[../references/env-layouts.md](../references/env-layouts.md).

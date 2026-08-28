# Validation

Run validation without reading secret files and without live HTTP requests.

## Contents

- [Asset integrity](#asset-integrity)
- [Static checks](#static-checks)
- [Mock test suite](#mock-test-suite)
- [What the suite covers](#what-the-suite-covers)
- [Extending the suite](#extending-the-suite)
- [Fastlane checks](#fastlane-checks)
- [CI checks](#ci-checks)
- [Going live](#going-live)

## Asset integrity

Immediately after copying:

```bash
cmp <skill-path>/assets/fastlane/publish_notion_release.sh \
  fastlane/publish_notion_release.sh
cmp <skill-path>/assets/fastlane/send_discord_release_notification.sh \
  fastlane/send_discord_release_notification.sh
```

If project-specific behavior is required, establish this clean baseline first,
then modify only the project copies.

## Static checks

```bash
bash -n fastlane/publish_notion_release.sh
bash -n fastlane/send_discord_release_notification.sh
ruby -c fastlane/Fastfile
bundle exec fastlane lanes
circleci config validate .circleci/config.yml
git diff --check
git status --short          # no decoded env file may appear here
```

Run the repository's required formatter or linter for any edited Ruby code. If a
tool is unavailable in the environment, say so rather than reporting that the
check passed.

## Mock test suite

The skill ships a harness that stands up mock Notion and Discord endpoints and
asserts the behavior that matters. Run it against the project's copies:

```bash
bash <skill-path>/scripts/run_mock_tests.sh fastlane
```

Omit the argument to validate the skill's own assets. The harness needs only
`bash` and `jq`; it never touches the network, never reads a `.env` file, and
uses obviously fake identifiers throughout. It exits non-zero when any assertion
fails and prints one line per assertion.

Run it after copying the assets, after any edit to either script, and before
handing the integration back to the user. Writing bespoke mocks by hand for each
project wastes time and tends to miss exactly the degraded-input cases that
break real releases.

## What the suite covers

| Case | Assertion |
| --- | --- |
| All three sections populated | Counts are correct, backlog is returned for Discord, backlog owners stay out of the mention list |
| Empty and placeholder sections | Publishing still succeeds, empty headings are omitted, placeholders are never looked up in Notion |
| Unknown heading | Content is preserved as plain text instead of aborting |
| Build information only | A release page is still created |
| Discord with backlog | Backlog field is present, resolved entries link, unresolved entries stay plain |
| Discord without backlog | Backlog field is omitted, the unassigned fallback is used |
| Assignee mapping | `allowed_mentions.users` holds only mapped numeric IDs; unmapped names stay as text |

## Extending the suite

Add a case when the project introduces behavior the defaults do not cover — a
different release-note dialect, an extra Discord field, a second bug data
source. The mock `curl` in the harness routes by URL and returns a match for any
lookup key containing `Known`, which is enough to exercise both the resolved and
unresolved paths.

Behavior worth asserting that the shipped cases do not yet cover, if a project
depends on it:

- Requests are 400–500 ms apart and retries are bounded.
- A `429` or transient `5xx` is retried, then degrades to plain text rather than
  aborting.
- Two matching candidates leave the item unresolved without a task URL.
- Assignee extraction picks the first existing people property from
  `NOTION_ASSIGNEE_PROPERTY_NAMES_JSON`, including when task and bug sources use
  different property names.
- Configuration failures and release-page creation failures remain fatal.
- A non-HTTPS webhook URL and a non-2xx Discord response both fail loudly.

## Fastlane checks

Run lane parsing first:

```bash
bundle exec fastlane lanes
```

Then run the notification-only lane with mocked script executables or mocked
HTTP:

```bash
bundle exec fastlane <platform> publish_current_release_notifications --env <environment>
```

Confirm:

- The lane supplies platform, environment, version, and build number.
- `Open3.capture3` keeps JSON stdout separate from stderr.
- Notion runs before Discord.
- Discord receives the exact Notion URL, unique assignees, and the backlog list
  straight from the Notion result.
- Notification failure does not rerun or invalidate an already successful build.

## CI checks

- The config validates and every referenced lane exists.
- Every `SECRET_FILES` destination is a path this project actually reads, and
  every referenced CI variable exists in the project settings.
- The env file reaches the process environment Fastlane runs in — either through
  Fastlane's own dotenv or an explicit load step.
- Each job installs `curl`, `jq`, Ruby/Bundler, and the platform toolchain.
- Secrets come from the provider's encrypted store, and no step echoes them.
- Branch filters match the team's release convention.
- The notification-only job can run without the build job.

## Going live

Request explicit user authorization before replacing mocks with live Notion or
Discord endpoints, and prefer a non-production flavor with a low-stakes channel
for the first real run.

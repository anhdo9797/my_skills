# Validation

Run validation without reading secret files and without live HTTP requests.

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
rtk bash -n fastlane/publish_notion_release.sh
rtk bash -n fastlane/send_discord_release_notification.sh
rtk bundle exec fastlane lanes
rtk git diff --check
```

Run the repository's required formatter or linter for any edited Ruby code.

## Mock Notion

Set `CURL_BIN` and `SLEEP_BIN` to test doubles in a temporary test directory.
The mock curl executable should:

1. Record request timestamps and sanitized endpoints.
2. Return fixture JSON for data-source queries and page creation.
3. Simulate `429` and transient `5xx` responses.
4. Never print authorization headers.

Verify:

- Requests after the first are 400–500 ms apart.
- Retries are bounded.
- A specific bug prefix such as `iOS New [BUG 10]` is queried before broad
  `[BUG 10]` and `BUG 10` fallbacks.
- Missing tasks stay as unresolved plain text.
- Query payloads use `page_size: 2`.
- Two matching candidates stay as unresolved raw text without a task URL, and
  do not abort release-page creation.
- Malformed responses and exhausted per-task lookup failures stay as unresolved
  raw text without a task URL.
- Assignee extraction selects the first existing `people` property from
  `NOTION_ASSIGNEE_PROPERTY_NAMES_JSON`, including when task and bug sources use
  different property names.
- When more than one configured people property exists on a page, only the
  highest-priority property contributes assignees.
- Configuration failures and release-page creation failures remain fatal.
- Duplicate assignee names appear once.
- Success JSON includes `release_page_url`, `assignees`, `summary`, and `items`.
- Operational logs go to stderr; stdout remains valid JSON.

## Mock Discord

Use a mock `CURL_BIN` that captures the request body and returns a successful
webhook response. Verify with `jq`:

- Embed author renders `APP_NAME` and environment.
- Version/build, Notion link, assignees, action text, footer, and timestamp are
  present exactly once.
- Mapped assignees render as `<@id>`.
- Unmapped assignees retain their original names.
- Duplicates appear once.
- `allowed_mentions.users` contains only mapped numeric IDs.
- No image, thumbnail, duplicate title, or duplicate description is added.

Also test invalid JSON, a non-HTTPS webhook URL, an empty required value, and a
non-2xx Discord response.

## Fastlane checks

Run lane parsing first:

```bash
rtk bundle exec fastlane lanes
```

Then run the notification-only lane with mocked script executables or mocked
HTTP:

```bash
rtk bundle exec fastlane <platform> <notification_lane> --env <environment>
```

Confirm:

- The lane supplies platform, environment, version, and build number.
- `Open3.capture3` keeps JSON stdout separate from stderr.
- Notion runs before Discord.
- Discord receives the exact Notion URL and unique assignees.
- Notification failure does not rerun or invalidate an already successful build.

Request explicit user authorization before replacing mocks with live Notion or
Discord endpoints.

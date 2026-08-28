# Environment Configuration

## Contents

- [Security boundary](#security-boundary)
- [Notion setup](#notion-setup)
- [Discord setup](#discord-setup)
- [Variable reference](#variable-reference)
- [Fastlane and CI setup](#fastlane-and-ci-setup)
- [CircleCI variables](#circleci-variables)
- [Release-note input](#release-note-input)

## Security boundary

Never read, display, copy, or commit actual `.env*` contents, webhook URLs,
tokens, keys, or certificates. Guide the user to set values in their local
Fastlane environment and CI secret store. Documentation examples must use
obviously fake values.

Treat these as secrets:

- `NOTION_API_TOKEN`
- `DISCORD_WEBHOOK_URL`

Treat identifiers and display configuration as non-secret unless the target
organization has a stricter policy.

## Notion setup

Guide the user through these steps in the Notion UI:

1. Create an internal integration in the workspace that owns the release and
   task pages.
2. Copy its integration token into the local/CI secret named
   `NOTION_API_TOKEN`.
3. Share the parent release page, task data source, and bug data source with the
   integration.
4. Copy the parent page ID from its URL.
5. Copy each data-source ID from the Notion UI/API. A database ID is not always
   interchangeable with a data-source ID in current Notion APIs.
6. Identify the task title property ID or exact name.
7. Identify every possible people-property exact name across the task and bug
   sources. Configure them in priority order as a JSON array, for example
   `["Assignee","Assignee to"]`; do not append `.name`.

The integration needs read access to task/bug sources and create access under
the configured parent page.

## Discord setup

Guide the user through these steps:

1. Open the destination server/channel integration settings.
2. Create a webhook and store its HTTPS URL as the `DISCORD_WEBHOOK_URL` secret.
3. Choose a reusable webhook username and optional HTTPS avatar URL.
4. Enable Discord Developer Mode when user IDs are needed.
5. Copy each member ID and create a JSON object whose keys exactly match Notion
   display names.

Example with fake IDs:

```json
{
  "Example User": "100000000000000001",
  "Second User": "100000000000000002"
}
```

Mapped names render as mentions and appear in `allowed_mentions.users`.
Unmapped names remain unchanged as plain text. An empty assignee list uses
`DISCORD_UNASSIGNED_FALLBACK`.

## Variable reference

### Shared and Notion

| Variable | Required | Secret | Purpose |
| --- | --- | --- | --- |
| `APP_NAME` | Yes | No | App name used in Notion and Discord templates. |
| `APP_EMOJI` | Yes | No | One valid Notion emoji for the release page icon. |
| `RELEASE_PAGE_TITLE` | No | No | Notion title prefix; defaults to `APP_NAME`. |
| `NOTION_API_TOKEN` | Yes | Yes | Internal integration token. |
| `NOTION_PARENT_PAGE_ID` | Yes | No | Parent page for release pages. |
| `NOTION_TASK_DATA_SOURCE_ID` | Yes | No | Task data-source ID. |
| `NOTION_BUG_DATA_SOURCE_ID` | Yes | No | Bug data-source ID. |
| `NOTION_TITLE_PROPERTY_ID` | Yes | No | Title property ID or exact name. |
| `NOTION_ASSIGNEE_PROPERTY_NAMES_JSON` | Yes | No | Ordered JSON array of people-property names; the first matching property is used. |
| `NOTION_ASSIGNEE_PROPERTY_NAME` | No | No | Deprecated single-property fallback. |
| `NOTION_REQUEST_INTERVAL_MS` | No | No | Delay between requests; `400`–`500`, default `450`. |
| `NOTION_MAX_ATTEMPTS` | No | No | Positive retry limit; default `4`. |
| `NOTION_RETRY_BASE_SECONDS` | No | No | Non-negative retry base; default `1`. |

### Discord

| Variable | Required | Secret | Purpose |
| --- | --- | --- | --- |
| `DISCORD_WEBHOOK_URL` | Yes | Yes | Destination HTTPS webhook URL. |
| `DISCORD_USERNAME` | Yes | No | Webhook display name. |
| `DISCORD_AVATAR_URL` | No | No | Optional HTTPS avatar URL. |
| `DISCORD_ASSIGNEE_MAP_JSON` | Yes | No | Exact Notion-name to numeric Discord-ID object. |
| `DISCORD_VERSION_LABEL` | No | No | Version field label; defaults to `⚙️ Version`. |
| `DISCORD_RELEASE_VERSION_TEMPLATE` | No | No | Supports `{{VERSION}}`, `{{BUILD_NUMBER}}`. |
| `DISCORD_RELEASE_NOTES_LABEL` | Yes | No | Release link field label. |
| `DISCORD_RELEASE_NOTES_VALUE_TEMPLATE` | No | No | Supports `{{RELEASE_URL}}`. |
| `DISCORD_BACKLOG_LABEL` | No | No | Backlog field label; defaults to `📌 Backlog`. |
| `DISCORD_BACKLOG_MAX_ITEMS` | No | No | Positive backlog item cap; default `10`. |
| `DISCORD_TASK_ASSIGNED_LABEL` | Yes | No | Assignee field label. |
| `DISCORD_ACTION_REQUIRED_TEXT` | Yes | No | Verification instruction. |
| `DISCORD_EMBED_COLOR` | No | No | Six-digit hex color; default `#2ECC71`. |
| `DISCORD_EMBED_AUTHOR_TEMPLATE` | No | No | Supports app and release metadata tokens. |
| `DISCORD_EMBED_FOOTER_TEMPLATE` | No | No | Supports app and release metadata tokens. |
| `DISCORD_UNASSIGNED_FALLBACK` | Yes | No | Plain text for an empty assignee list. |

Optional executable overrides for tests are `CURL_BIN`, `JQ_BIN`, and
`SLEEP_BIN` (Notion only). Do not set these in normal CI unless the image uses
nonstandard executable paths.

Recommended non-secret display values:

```sh
DISCORD_RELEASE_NOTES_LABEL="📋 Release notes"
DISCORD_TASK_ASSIGNED_LABEL="👥 Task assigned"
DISCORD_BACKLOG_LABEL="📌 Backlog"
DISCORD_ACTION_REQUIRED_TEXT="✅ **Yêu cầu:** Vui lòng xác minh các task được giao trước khi gửi bản build cho QC."
DISCORD_UNASSIGNED_FALLBACK="Chưa phân công"
DISCORD_EMBED_AUTHOR_TEMPLATE="{{APP_NAME}} release {{ENVIRONMENT}}"
DISCORD_EMBED_FOOTER_TEMPLATE="{{APP_NAME}} • {{PLATFORM}} • {{ENVIRONMENT}}"
```

## Fastlane and CI setup

Use one source of truth per value:

- Fastlane's selected environment supplies project configuration.
- The platform lane supplies platform.
- The completed build supplies version and build number.
- CI secret storage supplies tokens and webhook URLs.

For local use, the user may configure Fastlane dotenv files or export variables
in their shell. Do not create an actual `.env` file on the user's behalf and do
not inspect one. Provide names and example values only.

For CI:

1. Add secret values through the provider's protected/encrypted variable UI.
2. Add non-secret identifiers and display values through project variables or
   the same protected store if required by policy.
3. Pass the selected Fastlane environment explicitly, for example `--env prod`.
4. Install Bash, curl, jq, Ruby/Bundler, and Fastlane in the job image.
5. Mask secrets and avoid `set -x`.

Do not commit a mapping containing real organization member IDs unless the user
confirms that repository policy allows it.

`examples/flutter-circleci-firebase/fastlane/env.prod.example` lists every name
in one place. Copy it to the project's own env location with an `.example`
suffix, keep it committed with empty values, and have the user fill in the real
file locally. That location is project-specific — see
[env-layouts.md](env-layouts.md) before choosing it.

## CircleCI variables

The reference pipeline injects the entire dotenv file as one base64 CI variable
per environment rather than declaring each name separately:

| CI variable | Contents |
| --- | --- |
| `ENV_DEV_FILE` | base64 of the project's dev env file |
| `ENV_PROD_FILE` | base64 of the project's prod env file |

Non-dotenv secrets travel the same way: keystores, `key.properties`, the App
Store Connect `.p8`, and Firebase config files. Each job declares where its
files land through `SECRET_FILES`.

```bash
base64 -i fastlane/.env.prod   # macOS
base64 -w0 fastlane/.env.prod  # Linux
```

One variable per environment keeps CI and local runs on the same source of
truth. Twenty individually declared CI variables drift from the local dotenv
within a release or two, and the drift only shows up as a failed release.

Use a CircleCI context when several repositories share the same Notion
integration or Discord webhook. See
[circleci-integration.md](circleci-integration.md) for job structure and the
tooling each executor needs, and [env-layouts.md](env-layouts.md) for choosing
the decode destinations.

## Release-note input

The Notion asset accepts UTF-8 text with up to three optional sections:

```text
🧩 Features:
- Feature task title

🐞 Bug Fixed:
- iOS New [BUG 10] - Bug title

📌 Backlog:
- Deferred task title
```

Pass platform, version, build number, and environment as CLI arguments from
Fastlane. Do not duplicate those values in the release-note file.

Empty sections, placeholder bullets, and unknown headings are handled without
failing the release. When a task cannot be resolved, the script keeps its
original text in the Notion release page rather than dropping it. See
[release-notes-format.md](release-notes-format.md) for the complete rules.

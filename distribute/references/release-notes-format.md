# Release-Note Format

## Contents

- [The three sections](#the-three-sections)
- [Why parsing is forgiving](#why-parsing-is-forgiving)
- [Item resolution](#item-resolution)
- [What reaches Notion](#what-reaches-notion)
- [What reaches Discord](#what-reaches-discord)
- [Script output contract](#script-output-contract)

## The three sections

`release_notes.txt` is UTF-8 text with up to three sections. None of them is
mandatory:

```text
🧩 Features:
- Task title as it appears in Notion

🐞 Bug Fixed:
- Android New [BUG 10] - Crash when opening the camera

📌 Backlog:
- Task deferred to the next build
```

Headings are matched case-insensitively after any leading emoji or symbol is
dropped, so all of these select the same section:

| Section | Accepted headings |
| --- | --- |
| Feature | `Feature:`, `Features:`, `🧩 Features:`, `New features:`, `Tính năng:` |
| Bug | `Bug:`, `Bugs:`, `Bug Fixed:`, `🐞 Bug Fixed:`, `Bug fixes:`, `Lỗi:`, `Sửa lỗi:` |
| Backlog | `Backlog:`, `📌 Backlog:`, `Pending:`, `Todo:`, `Tồn đọng:` |

Platform, version, build number, and environment are supplied by Fastlane as CLI
arguments. Metadata lines at the top of the file (`Platform: Android`) are still
read for local runs, but the CLI values win.

## Why parsing is forgiving

A build that already shipped to testers is worth recording even when its notes
are untidy. Aborting the publish step would leave the team with a distributed
build and no release page, which is strictly worse than a release page with a
thin body. So the parser degrades instead of failing:

| Input | Behavior |
| --- | --- |
| A section heading with no bullets | Section is skipped; no empty heading in Notion. |
| A placeholder bullet (`- N/A`, `- None`, `- Không có`, `- -`) | Item is dropped before any Notion lookup, so it never reports a missing task. |
| A missing section entirely | Skipped. |
| An unknown heading such as `Improvements:` | Heading and its bullets are copied verbatim into an **Other notes** section. |
| A non-bullet line inside a section | Copied verbatim into **Other notes**. |
| A bullet before any heading | Copied verbatim into **Other notes**. |
| No recognizable content at all | The release page is still created with build information; stderr carries a warning. |

Only these remain fatal, because they mean the release cannot be recorded at
all: a missing release-note file, missing configuration or token, invalid
release metadata, and a failed release-page creation.

Every degraded case writes a `[WARNING]` or `[INFO]` line to stderr. Fastlane
surfaces those through `UI.command_output`, so a thin release page always has a
visible reason in the job log.

## Item resolution

Feature and backlog entries are looked up in `NOTION_TASK_DATA_SOURCE_ID`; bug
entries in `NOTION_BUG_DATA_SOURCE_ID`.

- A leading platform prefix (`iOS`, `Android`, `[App iOS]`) is stripped before
  the lookup, since it belongs to the release note rather than the task title.
- Features and backlog entries fall back to the text before the first quote when
  the full title finds nothing.
- Bugs are looked up by the most specific prefix first (`iOS New [BUG 10]`),
  then `[BUG 10]`, then `BUG 10`.
- At most two candidates are requested. Zero, two, or a malformed response all
  leave the item as plain text with no link — never as an error.

Backlog owners are deliberately excluded from the assignee list. The Discord
message asks people to verify the build that just shipped, and backlog work is
by definition not in it.

## What reaches Notion

The release page contains a build-information block followed by only the
sections that have content:

```markdown
## Build information

- **Project:** Example App
- **Platform:** Android
- **Environment:** Production
- **Version:** 1.4.0
- **Build:** 42
- **Published at:** 09:30 27/08/2026

## 🧩 Features

- [Task title](https://www.notion.so/...)

## 📌 Backlog

- Deferred task title
```

Resolved items render as links; unresolved items render as plain bullets so the
text is never lost.

## What reaches Discord

The embed always carries version, the Notion link, assignees, and the action
text. The backlog field appears only when the release has backlog entries, is
capped at `DISCORD_BACKLOG_MAX_ITEMS` (default 10) with a `+N more` line, and is
truncated before Discord's 1024-character field limit.

## Script output contract

`publish_notion_release.sh` writes one JSON document to stdout and all logs to
stderr:

```json
{
  "success": true,
  "release_page_id": "…",
  "release_page_url": "https://www.notion.so/…",
  "assignees": ["Example User"],
  "summary": {"features": 1, "bugs": 1, "backlog": 2, "resolved": 3, "unresolved": 1},
  "items": [{"source_type": "backlog", "original_text": "…", "notion_url": null, "status": "unresolved"}],
  "backlog": [{"text": "…", "url": null}]
}
```

`backlog` is the ready-to-forward shape for `send_discord_release_notification.sh
--backlog-json`. Pass it through rather than re-deriving it from `items`, and
never re-read the release-note file in Fastlane.

On failure the script writes `{"success": false, "error": {"code", "message",
"details"}}` and exits non-zero. Error codes: `INVALID_ARGUMENT`,
`INVALID_CONFIGURATION`, `INVALID_RELEASE_NOTE`, `NOTION_TOKEN_MISSING`,
`NOTION_UNAUTHORIZED`, `NOTION_NOT_FOUND`, `NOTION_RATE_LIMITED`,
`NOTION_REQUEST_FAILED`, `CREATE_PAGE_FAILED`.

#!/usr/bin/env bash

# Exercise the release notification scripts against mocked Notion and Discord
# endpoints.
#
# Every project that integrates this skill needs the same reassurance before a
# real release runs: odd release notes must not abort the pipeline, and the
# Discord payload must contain exactly the fields the team expects. Rebuilding
# those mocks by hand each time is slow and easy to get subtly wrong, so they
# live here.
#
# Usage:
#   bash scripts/run_mock_tests.sh [path-to-fastlane-scripts-directory]
#
# The optional argument points at the directory holding the copied
# publish_notion_release.sh and send_discord_release_notification.sh. It
# defaults to this skill's assets/fastlane directory, which lets the same
# harness validate either the skill defaults or a project's copies.

set -uo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly DEFAULT_TARGET_DIR="$SCRIPT_DIR/../assets/fastlane"
TARGET_DIR="$(cd "${1:-$DEFAULT_TARGET_DIR}" && pwd)"

readonly NOTION_SCRIPT="$TARGET_DIR/publish_notion_release.sh"
readonly DISCORD_SCRIPT="$TARGET_DIR/send_discord_release_notification.sh"

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/distribute-mock-tests.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT

PASS_COUNT=0
FAIL_COUNT=0

# Report one assertion result and keep the suite running.
check() {
  local description="$1"
  local status="$2"

  if ((status == 0)); then
    PASS_COUNT=$((PASS_COUNT + 1))
    printf '  ok   %s\n' "$description"
  else
    FAIL_COUNT=$((FAIL_COUNT + 1))
    printf '  FAIL %s\n' "$description"
  fi
}

# Assert that a jq filter is true for a JSON document.
check_jq() {
  local description="$1"
  local json="$2"
  local filter="$3"

  jq -e "$filter" >/dev/null 2>&1 <<< "$json"
  check "$description" $?
}

# Create the mock curl, sleep, and fixture files used by every case.
setup_mocks() {
  mkdir -p "$WORK_DIR/bin"

  cat > "$WORK_DIR/bin/curl" <<'MOCK_EOF'
#!/usr/bin/env bash
set -uo pipefail

url=""
output_file=""
header_file=""
payload=""

while (($# > 0)); do
  case "$1" in
    --url) url="$2"; shift 2 ;;
    --output) output_file="$2"; shift 2 ;;
    --dump-header) header_file="$2"; shift 2 ;;
    --data-binary) payload="$2"; shift 2 ;;
    --header|--connect-timeout|--max-time|--request|--write-out) shift 2 ;;
    *) shift ;;
  esac
done

[[ -n "$header_file" ]] && : > "$header_file"

capture_dir="${MOCK_CAPTURE_DIR:?MOCK_CAPTURE_DIR is required}"
mkdir -p "$capture_dir"

if [[ "$url" == *"/data_sources/"* ]]; then
  lookup="$(jq -r '.filter.title.contains // ""' <<< "$payload")"
  printf '%s\n' "$lookup" >> "$capture_dir/lookups.txt"
  if [[ "$lookup" == *"Known"* ]]; then
    cat > "$output_file" <<JSON
{
  "results": [
    {
      "id": "task-id-1",
      "url": "https://www.notion.so/task-id-1",
      "properties": {
        "Assignee": {
          "type": "people",
          "people": [{"name": "Example User"}]
        }
      }
    }
  ],
  "has_more": false
}
JSON
  else
    printf '{"results": [], "has_more": false}\n' > "$output_file"
  fi
  printf '200'
  exit 0
fi

if [[ "$url" == *"/pages"* ]]; then
  printf '%s' "$payload" > "$capture_dir/notion_page_request.json"
  printf '{"id": "release-page-id", "url": "https://www.notion.so/release-page-id"}\n' \
    > "$output_file"
  printf '200'
  exit 0
fi

if [[ "$url" == *"discord"* ]]; then
  printf '%s' "$payload" > "$capture_dir/discord_request.json"
  printf '{"id": "message-id"}\n' > "$output_file"
  printf '200'
  exit 0
fi

printf '{"error": "unexpected url"}\n' > "$output_file"
printf '404'
exit 0
MOCK_EOF

  cat > "$WORK_DIR/bin/sleep" <<'MOCK_EOF'
#!/usr/bin/env bash
exit 0
MOCK_EOF

  chmod +x "$WORK_DIR/bin/curl" "$WORK_DIR/bin/sleep"
}

# Export the non-secret configuration both scripts expect, with fake values.
export_common_env() {
  export APP_NAME="Example App"
  export APP_EMOJI="🚀"
  export NOTION_API_TOKEN="fake-notion-token"
  export NOTION_PARENT_PAGE_ID="00000000000000000000000000000000"
  export NOTION_TASK_DATA_SOURCE_ID="11111111111111111111111111111111"
  export NOTION_BUG_DATA_SOURCE_ID="22222222222222222222222222222222"
  export NOTION_TITLE_PROPERTY_ID="title"
  export NOTION_ASSIGNEE_PROPERTY_NAMES_JSON='["Assignee","Assignee to"]'
  export CURL_BIN="$WORK_DIR/bin/curl"
  export SLEEP_BIN="$WORK_DIR/bin/sleep"
  export JQ_BIN="jq"

  export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/000/fake"
  export DISCORD_USERNAME="Release Bot"
  export DISCORD_ASSIGNEE_MAP_JSON='{"Example User":"100000000000000001"}'
  export DISCORD_RELEASE_NOTES_LABEL="📋 Release notes"
  export DISCORD_TASK_ASSIGNED_LABEL="👥 Task assigned"
  export DISCORD_ACTION_REQUIRED_TEXT="Please verify the assigned tasks."
  export DISCORD_UNASSIGNED_FALLBACK="Unassigned"
}

# Run the Notion publisher against one release-note fixture.
run_notion() {
  local notes="$1"
  local capture_dir="$2"
  local notes_file="$capture_dir/release_notes.txt"

  mkdir -p "$capture_dir"
  printf '%s\n' "$notes" > "$notes_file"
  MOCK_CAPTURE_DIR="$capture_dir" bash "$NOTION_SCRIPT" \
    --input "$notes_file" \
    --platform "Android" \
    --version "1.4.0" \
    --build-number "42" \
    --environment "Production" \
    2> "$capture_dir/stderr.log"
}

printf 'Release notification mock tests\n'
printf 'Target: %s\n\n' "$TARGET_DIR"

setup_mocks
export_common_env

printf 'case: all three sections populated\n'
capture="$WORK_DIR/case-full"
output="$(run_notion '🧩 Features:
- Known feature title

🐞 Bug Fixed:
- Android Known [BUG 10] - Crash on startup

📌 Backlog:
- Known backlog item' "$capture")"
check "exits successfully" $?
check_jq "reports success" "$output" '.success == true'
check_jq "counts one feature, one bug, one backlog item" "$output" \
  '.summary.features == 1 and .summary.bugs == 1 and .summary.backlog == 1'
check_jq "returns the backlog list for Discord" "$output" \
  '(.backlog | length) == 1 and (.backlog[0].text | test("Known backlog"))'
check_jq "keeps backlog owners out of the mention list" "$output" \
  '.assignees == ["Example User"]'
markdown="$(jq -r '.markdown' "$capture/notion_page_request.json")"
check "renders the Features heading" \
  "$(grep -qF '## 🧩 Features' <<< "$markdown"; echo $?)"
check "renders the Backlog heading" \
  "$(grep -qF '## 📌 Backlog' <<< "$markdown"; echo $?)"

printf '\ncase: empty and placeholder sections\n'
capture="$WORK_DIR/case-empty"
output="$(run_notion '🧩 Features:

🐞 Bug Fixed:
- N/A

📌 Backlog:
- Known backlog item' "$capture")"
check "exits successfully" $?
check_jq "reports success" "$output" '.success == true'
check_jq "counts no features and no bugs" "$output" \
  '.summary.features == 0 and .summary.bugs == 0 and .summary.backlog == 1'
markdown="$(jq -r '.markdown' "$capture/notion_page_request.json")"
check "omits the empty Features heading" \
  "$(grep -qF '## 🧩 Features' <<< "$markdown"; echo $((1 - $?)))"
check "omits the placeholder Bug heading" \
  "$(grep -qF '## 🐞 Bug Fixed' <<< "$markdown"; echo $((1 - $?)))"
check "never looks up the placeholder bullet" \
  "$(grep -qiF 'n/a' "$capture/lookups.txt" 2>/dev/null; echo $((1 - $?)))"

printf '\ncase: unknown heading and stray bullets\n'
capture="$WORK_DIR/case-unknown"
output="$(run_notion 'Platform: Android
🧩 Features:
- Known feature title

Improvements:
- Faster cold start' "$capture")"
check "exits successfully" $?
check_jq "reports success" "$output" '.success == true'
markdown="$(jq -r '.markdown' "$capture/notion_page_request.json")"
check "keeps the unknown section as plain text" \
  "$(grep -qF 'Faster cold start' <<< "$markdown"; echo $?)"

printf '\ncase: build information only\n'
capture="$WORK_DIR/case-metadata-only"
output="$(run_notion 'Nothing shipped in this build.' "$capture")"
check "exits successfully" $?
check_jq "still publishes a release page" "$output" \
  '.success == true and (.release_page_url | length) > 0'

printf '\ncase: Discord payload with a backlog\n'
capture="$WORK_DIR/case-discord-backlog"
mkdir -p "$capture"
MOCK_CAPTURE_DIR="$capture" bash "$DISCORD_SCRIPT" \
  --release-url "https://www.notion.so/release-page-id" \
  --assignees-json '["Example User","Unmapped Person"]' \
  --backlog-json '[{"text":"Known backlog item","url":"https://www.notion.so/task-id-1"},"Plain backlog entry"]' \
  --platform "Android" \
  --version "1.4.0" \
  --build-number "42" \
  --environment "Production" \
  > "$capture/result.json" 2> "$capture/stderr.log"
check "exits successfully" $?
payload="$(cat "$capture/discord_request.json")"
check_jq "adds the backlog field" "$payload" \
  '[.embeds[0].fields[] | select(.name == "📌 Backlog")] | length == 1'
check_jq "links a resolved backlog entry" "$payload" \
  '.embeds[0].fields[] | select(.name == "📌 Backlog") | .value | test("\\[Known backlog item\\]")'
check_jq "keeps an unlinked backlog entry as plain text" "$payload" \
  '.embeds[0].fields[] | select(.name == "📌 Backlog") | .value | test("• Plain backlog entry")'
check_jq "mentions only mapped assignees" "$payload" \
  '.allowed_mentions.users == ["100000000000000001"]'
check_jq "keeps an unmapped assignee as plain text" "$payload" \
  '.embeds[0].fields[] | select(.name == "👥 Task assigned") | .value | test("Unmapped Person")'

printf '\ncase: Discord payload without a backlog\n'
capture="$WORK_DIR/case-discord-no-backlog"
mkdir -p "$capture"
MOCK_CAPTURE_DIR="$capture" bash "$DISCORD_SCRIPT" \
  --release-url "https://www.notion.so/release-page-id" \
  --assignees-json '[]' \
  --platform "iOS" \
  --version "1.4.0" \
  --build-number "42" \
  --environment "Production" \
  > "$capture/result.json" 2> "$capture/stderr.log"
check "exits successfully" $?
payload="$(cat "$capture/discord_request.json")"
check_jq "omits the backlog field" "$payload" \
  '[.embeds[0].fields[] | select(.name == "📌 Backlog")] | length == 0'
check_jq "uses the unassigned fallback" "$payload" \
  '.embeds[0].fields[] | select(.name == "👥 Task assigned") | .value == "Unassigned"'

printf '\n%d passed, %d failed\n' "$PASS_COUNT" "$FAIL_COUNT"
((FAIL_COUNT == 0))

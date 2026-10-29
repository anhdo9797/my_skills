#!/usr/bin/env bash

# Send a short pull request review notification to Discord.
#
# This is the bundled template. During onboarding the skill copies it into the
# project (folder chosen by the user), so it must stay self-contained and must
# not depend on its own location.
#
# Requirements:
#   - Bash 3.2+
#   - curl
#   - jq

set -euo pipefail

readonly FINDING_TITLE_LIMIT="120"
readonly DISPLAY_FINDING_LIMIT="10"
readonly WEBHOOK_VAR="DISCORD_WEBHOOK_REVIEW_CHANNEL"
CURL_BIN="${CURL_BIN:-curl}"
JQ_BIN="${JQ_BIN:-jq}"
PR_URL=""
REVIEW_JSON=""
ENV_FILE=""
PRINT_PAYLOAD="0"

# Print command usage.
usage() {
  printf '%s\n' \
    "Usage: send_discord_review_notification.sh --pr-url <url> --review-json <json> [--env-file <path>] [--print-payload]" \
    "" \
    'JSON: {"decision":"changes_requested","inline_comments":2,"findings":[{"severity":"major","title":"First issue"}]}' \
    "" \
    "Webhook lookup order (first non-empty wins):" \
    "  1. Exported $WEBHOOK_VAR (shell or Claude Code settings.json env block)" \
    "  2. --env-file <path>, or DISCORD_REVIEW_ENV_FILE (only the $WEBHOOK_VAR line is read)" \
    "" \
    "--print-payload prints the Discord JSON and exits without sending or needing a webhook."
}

# Fail with a concise message that never includes the webhook URL.
fail() {
  printf 'Error: %s\n' "$1" >&2
  exit 1
}

# Parse and validate the required command-line arguments.
parse_arguments() {
  while (($# > 0)); do
    case "$1" in
      --pr-url)
        [[ $# -ge 2 ]] || fail "--pr-url requires a value."
        PR_URL="$2"
        shift 2
        ;;
      --review-json)
        [[ $# -ge 2 ]] || fail "--review-json requires a value."
        REVIEW_JSON="$2"
        shift 2
        ;;
      --env-file)
        [[ $# -ge 2 ]] || fail "--env-file requires a value."
        ENV_FILE="$2"
        shift 2
        ;;
      --print-payload)
        PRINT_PAYLOAD="1"
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        fail "Unknown option. Use --help for usage."
        ;;
    esac
  done

  [[ -n "$PR_URL" ]] || fail "--pr-url is required."
  [[ -n "$REVIEW_JSON" ]] || fail "--review-json is required."
}

# Validate the review schema and reject malformed input before making a request.
validate_review() {
  "$JQ_BIN" -en --arg url "$PR_URL" '
    $url | length <= 512 and
    test("\\Ahttps://[A-Za-z0-9.-]+(:[0-9]{1,5})?/[A-Za-z0-9_./~-]+/pull-requests/[0-9]{1,20}/?\\z")
  ' >/dev/null 2>&1 || fail "--pr-url must be a valid HTTPS Bitbucket pull request URL."

  printf '%s' "$REVIEW_JSON" | "$JQ_BIN" -es '
    def valid_finding:
      if type != "object" then false
      else (.severity | IN("blocker", "major", "minor", "suggestion", "question")) and
        (if (.title | type) != "string" then false
         else (.title | test("\\S")) end)
      end;
    if length != 1 or (.[0] | type) != "object" then false
    else .[0] |
      if (.findings | type) != "array" or (.inline_comments | type) != "number" then false
      else (.decision | IN("changes_requested", "need_clarification", "approve_with_suggestions", "approve")) and
        (.findings | length <= 10000) and
        (.inline_comments >= 0 and .inline_comments == (.inline_comments | floor)) and
        (.inline_comments <= (.findings | length)) and
        all(.findings[]; valid_finding) and
        (if any(.findings[]; .severity == "blocker" or .severity == "major") then
           .decision == "changes_requested"
         elif (.findings | length) == 0 then .decision == "approve"
         elif any(.findings[]; .severity == "question") then
           (.decision == "need_clarification" or .decision == "changes_requested")
         else .decision != "approve" end)
      end
    end
  ' >/dev/null 2>&1 || fail "Invalid review JSON. Check decision, findings (severity/title), and actual inline_comments count."
}

# Build one embed with complete counts and bounded, sanitized finding summaries.
build_payload() {
  printf '%s' "$REVIEW_JSON" | "$JQ_BIN" -c \
    --arg url "$PR_URL" \
    --argjson title_limit "$FINDING_TITLE_LIMIT" \
    --argjson display_limit "$DISPLAY_FINDING_LIMIT" '
    def rank: {blocker: 0, major: 1, minor: 2, question: 3, suggestion: 4}[.severity];
    def severity_label: {blocker: "Blocker", major: "Major", minor: "Minor", question: "Question", suggestion: "Suggestion"}[.severity];
    def short_title:
      gsub("[[:cntrl:]]"; " ") | gsub("[*_`~<>\\[\\]\\\\|]"; "") |
      gsub("\\s+"; " ") | sub("^ +"; "") | sub(" +$"; "") |
      if length > $title_limit then .[0:($title_limit - 1)] + "…" else . end;
    . as $review |
    (.findings | sort_by(rank)) as $findings |
    (["blocker", "major", "minor"] | map(. as $severity |
      {key: $severity, value: ([$findings[] | select(.severity == $severity)] | length)}) | from_entries) as $counts |
    (if $counts.blocker > 0 then 10038562
     elif $counts.major > 0 then 15548997
     elif ($findings | length) > 0 then 16705372
     else 5763719 end) as $color |
    ({changes_requested: "🔴 **Changes requested**", need_clarification: "🟡 **Need clarification**",
      approve_with_suggestions: "🟡 **Approve with suggestions**", approve: "✅ **Review completed**"}[$review.decision] |
      if $counts.blocker > 0 then sub("🔴"; "🛑") else . end) as $message |
    ($url | capture("/pull-requests/(?<id>[0-9]+)").id) as $pr_number |
    {username: "Bitbucket Review Bot", allowed_mentions: {parse: []}, embeds: [{
      color: $color,
      title: ("🔍 PR #" + $pr_number + " · Code Review"),
      url: $url,
      description: ([ $message, "",
        (if ($findings | length) == 0 then "Không có vấn đề cần xử lý."
         else "**Vấn đề cần xử lý:**", "",
           ($findings[:$display_limit][] | "💬 **[" + severity_label + "] " + (.title | short_title) + "**"),
           (if ($findings | length) > $display_limit then
             "", ("… Còn " + (($findings | length) - $display_limit | tostring) + " vấn đề; xem PR.")
            else empty end)
         end)
      ] | join("\n")),
      fields: [
        {name: "🛑 Blocker", value: ("**" + ($counts.blocker | tostring) + "**"), inline: true},
        {name: "🔴 Major", value: ("**" + ($counts.major | tostring) + "**"), inline: true},
        {name: "🟡 Minor", value: ("**" + ($counts.minor | tostring) + "**"), inline: true}
      ],
      footer: {text: (($review.inline_comments | tostring) + " inline comments · Bitbucket Review Bot" | "💬 " + .)},
      timestamp: (now | todate)
    }]}
  '
}

# Send one bounded Discord message and fail without exposing webhook details.
send_notification() {
  local payload=""
  local http_code="000"
  payload="$(build_payload)" || fail "Could not build the Discord payload."

  if ! http_code="$(printf '%s' "$payload" | "$CURL_BIN" --silent --request POST \
    --url "$DISCORD_WEBHOOK_REVIEW_CHANNEL" \
    --header "Content-Type: application/json" \
    --connect-timeout 15 --max-time 30 \
    --output /dev/null --write-out '%{http_code}' \
    --data-binary @- 2>/dev/null)"; then
    fail "Discord webhook request failed."
  fi
  [[ "$http_code" =~ ^2[0-9][0-9]$ ]] || fail "Discord webhook request failed (HTTP $http_code)."
}

# Read only the webhook line from a dotenv-style file. The file is never
# sourced, so other lines cannot execute and no other value is exposed.
load_webhook_configuration() {
  [[ -z "${DISCORD_WEBHOOK_REVIEW_CHANNEL:-}" ]] || return 0

  local file="${ENV_FILE:-${DISCORD_REVIEW_ENV_FILE:-}}"
  [[ -n "$file" ]] || return 0
  [[ "$file" == "~/"* ]] && file="$HOME/${file#\~/}"
  [[ -f "$file" ]] || fail "Env file not found: $file"

  local value=""
  value="$(grep -E "^(export[[:space:]]+)?${WEBHOOK_VAR}=" "$file" 2>/dev/null | tail -n 1 |
    sed -E "s/^(export[[:space:]]+)?${WEBHOOK_VAR}=//; s/^\"(.*)\"\$/\\1/; s/^'(.*)'\$/\\1/" || true)"
  DISCORD_WEBHOOK_REVIEW_CHANNEL="$value"
}

# Validate configuration and run the notification workflow.
main() {
  parse_arguments "$@"
  command -v "$JQ_BIN" >/dev/null 2>&1 || fail "Missing required command: $JQ_BIN."
  validate_review

  if [[ "$PRINT_PAYLOAD" == "1" ]]; then
    build_payload
    exit 0
  fi

  command -v "$CURL_BIN" >/dev/null 2>&1 || fail "Missing required command: $CURL_BIN."
  load_webhook_configuration
  DISCORD_WEBHOOK_REVIEW_CHANNEL="${DISCORD_WEBHOOK_REVIEW_CHANNEL:-}"
  [[ -n "$DISCORD_WEBHOOK_REVIEW_CHANNEL" ]] || fail "$WEBHOOK_VAR is required."
  [[ "$DISCORD_WEBHOOK_REVIEW_CHANNEL" =~ ^https:// ]] || fail "$WEBHOOK_VAR must use HTTPS."
  send_notification
}

main "$@"

#!/usr/bin/env bash

# Send a Fastlane release notification through a Discord webhook.
#
# Requirements:
#   - Bash 3.2+
#   - curl
#   - jq

set -euo pipefail

readonly DEFAULT_CURL_BIN="curl"
readonly DEFAULT_JQ_BIN="jq"
readonly DEFAULT_DISCORD_VERSION_LABEL="⚙️ Version"
readonly DEFAULT_DISCORD_RELEASE_VERSION_TEMPLATE='{{VERSION}} (Build {{BUILD_NUMBER}})'
readonly DEFAULT_DISCORD_RELEASE_NOTES_VALUE_TEMPLATE='[Mở bài viết trên Notion]({{RELEASE_URL}})'
readonly DEFAULT_DISCORD_EMBED_COLOR="#2ECC71"
readonly DEFAULT_DISCORD_EMBED_AUTHOR_TEMPLATE='{{APP_NAME}} release {{ENVIRONMENT}}'
readonly DEFAULT_DISCORD_EMBED_FOOTER_TEMPLATE='{{APP_NAME}} • {{PLATFORM}} • {{ENVIRONMENT}}'

CURL_BIN="${CURL_BIN:-$DEFAULT_CURL_BIN}"
JQ_BIN="${JQ_BIN:-$DEFAULT_JQ_BIN}"

RELEASE_URL=""
ASSIGNEES_JSON='[]'
RELEASE_PLATFORM=""
RELEASE_VERSION=""
RELEASE_BUILD_NUMBER=""
RELEASE_ENVIRONMENT=""

# Print command usage.
usage() {
  printf '%s\n' \
    "Usage: fastlane/send_discord_release_notification.sh [options]" \
    "" \
    "Options:" \
    "  --release-url <url>       Required Notion release page URL" \
    "  --assignees-json <json>   Required JSON array of Notion assignee names" \
    "  --platform <value>        Required release platform" \
    "  --version <value>         Required release version" \
    "  --build-number <value>    Required release build number" \
    "  --environment <value>     Required release environment" \
    "  -h, --help                Show this help" \
    "" \
    "Environment:" \
    "  APP_NAME                           Required app name" \
    "  DISCORD_WEBHOOK_URL                Required Discord webhook URL" \
    "  DISCORD_USERNAME                   Required Discord webhook display name" \
    "  DISCORD_AVATAR_URL                 Optional Discord webhook avatar URL" \
    "  DISCORD_ASSIGNEE_MAP_JSON          Required JSON object: Notion name -> Discord user ID" \
    "  DISCORD_VERSION_LABEL              Optional label rendered before the version line" \
    "  DISCORD_RELEASE_VERSION_TEMPLATE   Optional template with {{VERSION}}, {{BUILD_NUMBER}}" \
    "  DISCORD_RELEASE_NOTES_LABEL        Required release-notes label" \
    "  DISCORD_RELEASE_NOTES_VALUE_TEMPLATE Optional template with {{RELEASE_URL}}" \
    "  DISCORD_TASK_ASSIGNED_LABEL        Required assignee label" \
    "  DISCORD_ACTION_REQUIRED_TEXT       Required action-required text" \
    "  DISCORD_EMBED_COLOR                Optional six-digit hex color, such as #2ECC71" \
    "  DISCORD_EMBED_AUTHOR_TEMPLATE      Optional template with release metadata tokens" \
    "  DISCORD_EMBED_FOOTER_TEMPLATE      Optional template with release metadata tokens" \
    "  DISCORD_UNASSIGNED_FALLBACK        Required plain-text fallback when there are no assignees"
}

# Emit a structured error without exposing secret values.
emit_error() {
  local error_code="$1"
  local message="$2"
  local details="${3:-}"

  if command -v "$JQ_BIN" >/dev/null 2>&1; then
    "$JQ_BIN" -n \
      --arg code "$error_code" \
      --arg message "$message" \
      --arg details "$details" \
      '{success: false, error: {code: $code, message: $message, details: (if $details == "" then null else $details end)}}'
  else
    printf '[ERROR] %s: %s\n' "$error_code" "$message" >&2
  fi

  exit 1
}

# Ensure an executable is available.
require_command() {
  local command_name="$1"
  local install_hint="$2"

  if ! command -v "$command_name" >/dev/null 2>&1; then
    emit_error "MISSING_COMMAND" "Missing required command: $command_name." "$install_hint"
  fi
}

# Ensure a configuration value is present without printing it.
require_configuration() {
  local name="$1"
  local value="$2"

  [[ -n "$value" ]] || emit_error "INVALID_CONFIGURATION" "$name is required."
}

# Parse command-line arguments.
parse_arguments() {
  while (($# > 0)); do
    case "$1" in
      --release-url)
        [[ $# -ge 2 ]] || emit_error "INVALID_ARGUMENT" "--release-url requires a value."
        RELEASE_URL="$2"
        shift 2
        ;;
      --assignees-json)
        [[ $# -ge 2 ]] || emit_error "INVALID_ARGUMENT" "--assignees-json requires a value."
        ASSIGNEES_JSON="$2"
        shift 2
        ;;
      --platform)
        [[ $# -ge 2 ]] || emit_error "INVALID_ARGUMENT" "--platform requires a value."
        RELEASE_PLATFORM="$2"
        shift 2
        ;;
      --version)
        [[ $# -ge 2 ]] || emit_error "INVALID_ARGUMENT" "--version requires a value."
        RELEASE_VERSION="$2"
        shift 2
        ;;
      --build-number)
        [[ $# -ge 2 ]] || emit_error "INVALID_ARGUMENT" "--build-number requires a value."
        RELEASE_BUILD_NUMBER="$2"
        shift 2
        ;;
      --environment)
        [[ $# -ge 2 ]] || emit_error "INVALID_ARGUMENT" "--environment requires a value."
        RELEASE_ENVIRONMENT="$2"
        shift 2
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        emit_error "INVALID_ARGUMENT" "Unknown option: $1"
        ;;
    esac
  done
}

# Replace one literal token in a reusable title template.
replace_template_token() {
  local value="$1"
  local token="$2"
  local replacement="$3"

  printf '%s' "${value//$token/$replacement}"
}

# Render the configured Discord version text from release metadata.
render_release_version() {
  local template="$DISCORD_RELEASE_VERSION_TEMPLATE"

  template="$(replace_template_token "$template" '{{VERSION}}' "$RELEASE_VERSION")"
  replace_template_token "$template" '{{BUILD_NUMBER}}' "$RELEASE_BUILD_NUMBER"
}

# Render the configured embed author text from release metadata.
render_embed_author() {
  local template="$DISCORD_EMBED_AUTHOR_TEMPLATE"

  template="$(replace_template_token "$template" '{{APP_NAME}}' "$APP_NAME")"
  template="$(replace_template_token "$template" '{{ENVIRONMENT}}' "$RELEASE_ENVIRONMENT")"
  template="$(replace_template_token "$template" '{{PLATFORM}}' "$RELEASE_PLATFORM")"
  template="$(replace_template_token "$template" '{{VERSION}}' "$RELEASE_VERSION")"
  replace_template_token "$template" '{{BUILD_NUMBER}}' "$RELEASE_BUILD_NUMBER"
}

# Render the configured release-notes field value with the Notion release URL.
render_release_notes_value() {
  replace_template_token \
    "$DISCORD_RELEASE_NOTES_VALUE_TEMPLATE" '{{RELEASE_URL}}' "$RELEASE_URL"
}

# Render the configured embed footer from release metadata.
render_embed_footer() {
  local template="$DISCORD_EMBED_FOOTER_TEMPLATE"

  template="$(replace_template_token "$template" '{{APP_NAME}}' "$APP_NAME")"
  template="$(replace_template_token "$template" '{{ENVIRONMENT}}' "$RELEASE_ENVIRONMENT")"
  template="$(replace_template_token "$template" '{{PLATFORM}}' "$RELEASE_PLATFORM")"
  template="$(replace_template_token "$template" '{{VERSION}}' "$RELEASE_VERSION")"
  replace_template_token "$template" '{{BUILD_NUMBER}}' "$RELEASE_BUILD_NUMBER"
}

# Convert the configured hexadecimal embed color to the decimal value Discord expects.
parse_embed_color() {
  local color="${DISCORD_EMBED_COLOR#\#}"

  color="${color#0x}"
  color="${color#0X}"
  [[ "$color" =~ ^[0-9A-Fa-f]{6}$ ]] || emit_error \
    "INVALID_CONFIGURATION" "DISCORD_EMBED_COLOR must be a six-digit hexadecimal color."

  printf '%d' "0x$color"
}

# Render unique Discord mention tokens or plain-name fallbacks from Notion assignees.
render_assignees() {
  "$JQ_BIN" -cn \
    --argjson assignees "$ASSIGNEES_JSON" \
    --argjson assignee_map "$DISCORD_ASSIGNEE_MAP_JSON" \
    --arg fallback "$DISCORD_UNASSIGNED_FALLBACK" \
    '
      ($assignees | map(select(type == "string" and length > 0))) as $names
      | (if ($names | length) == 0 then [$fallback] else $names end)
      | reduce .[] as $name (
          [];
          ($assignee_map[$name] // null) as $discord_id
          | (if $discord_id == null then $name else "<@\($discord_id)>" end) as $rendered
          | if index($rendered) == null then . + [$rendered] else . end
        )'
}

# Render unique Discord user IDs that are allowed to receive a mention notification.
render_mentioned_user_ids() {
  "$JQ_BIN" -cn \
    --argjson assignees "$ASSIGNEES_JSON" \
    --argjson assignee_map "$DISCORD_ASSIGNEE_MAP_JSON" \
    '
      $assignees
      | map(select(type == "string" and length > 0))
      | map($assignee_map[.] // empty)
      | unique'
}

# Build a Discord embed webhook payload without images or thumbnail assets.
build_payload() {
  local embed_author="$1"
  local release_version="$2"
  local release_notes_value="$3"
  local assignees_text="$4"
  local footer="$5"
  local timestamp="$6"
  local color="$7"
  local mentioned_user_ids="$8"

  "$JQ_BIN" -n \
    --arg username "$DISCORD_USERNAME" \
    --arg avatar_url "$DISCORD_AVATAR_URL" \
    --arg author_name "$embed_author" \
    --arg version_label "$DISCORD_VERSION_LABEL" \
    --arg version "$release_version" \
    --arg release_notes_label "$DISCORD_RELEASE_NOTES_LABEL" \
    --arg release_notes_value "$release_notes_value" \
    --arg task_assigned_label "$DISCORD_TASK_ASSIGNED_LABEL" \
    --arg assignees "$assignees_text" \
    --arg action_required_text "$DISCORD_ACTION_REQUIRED_TEXT" \
    --arg footer "$footer" \
    --arg timestamp "$timestamp" \
    --argjson color "$color" \
    --argjson user_ids "$mentioned_user_ids" \
    '{
      username: $username,
      avatar_url: (if $avatar_url == "" then null else $avatar_url end),
      embeds: [{
        color: $color,
        author: {name: $author_name},
        fields: [
          {name: $version_label, value: ("**" + $version + "**"), inline: true},
          {name: $release_notes_label, value: $release_notes_value, inline: true},
          {name: $task_assigned_label, value: $assignees, inline: false},
          {name: "\u200b", value: $action_required_text, inline: false}
        ],
        footer: {text: $footer},
        timestamp: $timestamp
      }],
      allowed_mentions: {parse: [], users: $user_ids}
    }'
}

# Send one Discord webhook request and fail for a non-success response.
send_webhook() {
  local payload="$1"
  local body_file=""
  local http_code="000"
  local response_body=""
  local curl_exit=0

  body_file="$(mktemp "${TMPDIR:-/tmp}/discord-release-response.XXXXXX")"

  if http_code="$("$CURL_BIN" \
    --silent \
    --show-error \
    --request POST \
    --url "${DISCORD_WEBHOOK_URL}?wait=true" \
    --header "Content-Type: application/json" \
    --connect-timeout 15 \
    --max-time 60 \
    --output "$body_file" \
    --write-out '%{http_code}' \
    --data-binary "$payload")"; then
    curl_exit=0
  else
    curl_exit=$?
    http_code="000"
  fi

  if ((curl_exit != 0)) || [[ ! "$http_code" =~ ^2[0-9][0-9]$ ]]; then
    response_body="$(<"$body_file")"
    rm -f "$body_file"
    emit_error "DISCORD_REQUEST_FAILED" \
      "Discord webhook request failed with HTTP $http_code." \
      "${response_body:0:2000}"
  fi

  rm -f "$body_file"
}

# Validate script configuration and release input before creating a webhook payload.
validate_configuration() {
  require_configuration "APP_NAME" "$APP_NAME"
  require_configuration "DISCORD_WEBHOOK_URL" "$DISCORD_WEBHOOK_URL"
  require_configuration "DISCORD_USERNAME" "$DISCORD_USERNAME"
  require_configuration "DISCORD_ASSIGNEE_MAP_JSON" "$DISCORD_ASSIGNEE_MAP_JSON"
  require_configuration "DISCORD_VERSION_LABEL" "$DISCORD_VERSION_LABEL"
  require_configuration "DISCORD_RELEASE_VERSION_TEMPLATE" "$DISCORD_RELEASE_VERSION_TEMPLATE"
  require_configuration "DISCORD_RELEASE_NOTES_LABEL" "$DISCORD_RELEASE_NOTES_LABEL"
  require_configuration "DISCORD_RELEASE_NOTES_VALUE_TEMPLATE" "$DISCORD_RELEASE_NOTES_VALUE_TEMPLATE"
  require_configuration "DISCORD_TASK_ASSIGNED_LABEL" "$DISCORD_TASK_ASSIGNED_LABEL"
  require_configuration "DISCORD_ACTION_REQUIRED_TEXT" "$DISCORD_ACTION_REQUIRED_TEXT"
  require_configuration "DISCORD_EMBED_COLOR" "$DISCORD_EMBED_COLOR"
  require_configuration "DISCORD_EMBED_AUTHOR_TEMPLATE" "$DISCORD_EMBED_AUTHOR_TEMPLATE"
  require_configuration "DISCORD_EMBED_FOOTER_TEMPLATE" "$DISCORD_EMBED_FOOTER_TEMPLATE"
  require_configuration "DISCORD_UNASSIGNED_FALLBACK" "$DISCORD_UNASSIGNED_FALLBACK"
  require_configuration "--release-url" "$RELEASE_URL"
  require_configuration "--platform" "$RELEASE_PLATFORM"
  require_configuration "--version" "$RELEASE_VERSION"
  require_configuration "--build-number" "$RELEASE_BUILD_NUMBER"
  require_configuration "--environment" "$RELEASE_ENVIRONMENT"

  [[ "$DISCORD_WEBHOOK_URL" =~ ^https:// ]] || emit_error \
    "INVALID_CONFIGURATION" "DISCORD_WEBHOOK_URL must use HTTPS."
  "$JQ_BIN" -e 'type == "array" and all(.[]; type == "string")' \
    >/dev/null 2>&1 <<< "$ASSIGNEES_JSON" || emit_error \
    "INVALID_ARGUMENT" "--assignees-json must be a JSON array of strings."
  "$JQ_BIN" -e 'type == "object" and all(.[]; type == "string" and test("^[0-9]+$"))' \
    >/dev/null 2>&1 <<< "$DISCORD_ASSIGNEE_MAP_JSON" || emit_error \
    "INVALID_CONFIGURATION" "DISCORD_ASSIGNEE_MAP_JSON must map names to numeric Discord user IDs."
}

# Run the complete Discord release notification workflow.
main() {
  local embed_author=""
  local release_version=""
  local release_notes_value=""
  local rendered_assignees_json='[]'
  local rendered_assignees_text=""
  local mentioned_user_ids='[]'
  local footer=""
  local timestamp=""
  local color=""
  local payload=""

  parse_arguments "$@"
  require_command "$CURL_BIN" "Install curl in the CI image."
  require_command "$JQ_BIN" "Install jq in the CI image."

  APP_NAME="${APP_NAME:-}"
  DISCORD_WEBHOOK_URL="${DISCORD_WEBHOOK_URL:-}"
  DISCORD_USERNAME="${DISCORD_USERNAME:-}"
  DISCORD_AVATAR_URL="${DISCORD_AVATAR_URL:-}"
  DISCORD_ASSIGNEE_MAP_JSON="${DISCORD_ASSIGNEE_MAP_JSON:-}"
  DISCORD_VERSION_LABEL="${DISCORD_VERSION_LABEL:-$DEFAULT_DISCORD_VERSION_LABEL}"
  DISCORD_RELEASE_VERSION_TEMPLATE="${DISCORD_RELEASE_VERSION_TEMPLATE:-$DEFAULT_DISCORD_RELEASE_VERSION_TEMPLATE}"
  DISCORD_RELEASE_NOTES_LABEL="${DISCORD_RELEASE_NOTES_LABEL:-}"
  DISCORD_RELEASE_NOTES_VALUE_TEMPLATE="${DISCORD_RELEASE_NOTES_VALUE_TEMPLATE:-$DEFAULT_DISCORD_RELEASE_NOTES_VALUE_TEMPLATE}"
  DISCORD_TASK_ASSIGNED_LABEL="${DISCORD_TASK_ASSIGNED_LABEL:-}"
  DISCORD_ACTION_REQUIRED_TEXT="${DISCORD_ACTION_REQUIRED_TEXT:-}"
  DISCORD_EMBED_COLOR="${DISCORD_EMBED_COLOR:-$DEFAULT_DISCORD_EMBED_COLOR}"
  DISCORD_EMBED_AUTHOR_TEMPLATE="${DISCORD_EMBED_AUTHOR_TEMPLATE:-$DEFAULT_DISCORD_EMBED_AUTHOR_TEMPLATE}"
  DISCORD_EMBED_FOOTER_TEMPLATE="${DISCORD_EMBED_FOOTER_TEMPLATE:-$DEFAULT_DISCORD_EMBED_FOOTER_TEMPLATE}"
  DISCORD_UNASSIGNED_FALLBACK="${DISCORD_UNASSIGNED_FALLBACK:-}"

  validate_configuration

  embed_author="$(render_embed_author)"
  [[ -n "$embed_author" ]] || emit_error \
    "INVALID_CONFIGURATION" "DISCORD_EMBED_AUTHOR_TEMPLATE renders an empty author."
  release_version="$(render_release_version)"
  [[ -n "$release_version" ]] || emit_error \
    "INVALID_CONFIGURATION" "DISCORD_RELEASE_VERSION_TEMPLATE renders an empty version."
  release_notes_value="$(render_release_notes_value)"
  [[ -n "$release_notes_value" ]] || emit_error \
    "INVALID_CONFIGURATION" "DISCORD_RELEASE_NOTES_VALUE_TEMPLATE renders an empty value."
  rendered_assignees_json="$(render_assignees)"
  rendered_assignees_text="$("$JQ_BIN" -r 'join(", ")' <<< "$rendered_assignees_json")"
  mentioned_user_ids="$(render_mentioned_user_ids)"
  footer="$(render_embed_footer)"
  [[ -n "$footer" ]] || emit_error \
    "INVALID_CONFIGURATION" "DISCORD_EMBED_FOOTER_TEMPLATE renders an empty footer."
  timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  color="$(parse_embed_color)"

  payload="$(build_payload \
    "$embed_author" "$release_version" "$release_notes_value" \
    "$rendered_assignees_text" "$footer" "$timestamp" \
    "$color" "$mentioned_user_ids")"

  send_webhook "$payload"
  "$JQ_BIN" -n \
    --arg title "$embed_author" \
    --argjson assignees "$rendered_assignees_json" \
    --argjson mentioned_user_ids "$mentioned_user_ids" \
    '{success: true, title: $title, assignees: $assignees, mentioned_user_ids: $mentioned_user_ids}'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi

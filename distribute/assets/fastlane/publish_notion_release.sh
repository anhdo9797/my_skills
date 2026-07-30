#!/usr/bin/env bash

# Publish release notes to Notion using the Notion REST API.
#
# Requirements:
#   - Bash 3.2+
#   - curl
#   - jq
#   - NOTION_API_TOKEN environment variable

set -euo pipefail

readonly NOTION_API_VERSION="2026-03-11"
readonly NOTION_API_BASE_URL="https://api.notion.com/v1"
readonly DEFAULT_NOTION_REQUEST_INTERVAL_MS="450"

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly DEFAULT_INPUT_FILE="$PROJECT_ROOT/release_notes.txt"

CURL_BIN="${CURL_BIN:-curl}"
JQ_BIN="${JQ_BIN:-jq}"
SLEEP_BIN="${SLEEP_BIN:-sleep}"
NOTION_MAX_ATTEMPTS="${NOTION_MAX_ATTEMPTS:-4}"
NOTION_RETRY_BASE_SECONDS="${NOTION_RETRY_BASE_SECONDS:-1}"
NOTION_REQUEST_INTERVAL_MS="${NOTION_REQUEST_INTERVAL_MS:-$DEFAULT_NOTION_REQUEST_INTERVAL_MS}"
APP_NAME="${APP_NAME:-}"
RELEASE_PAGE_TITLE="${RELEASE_PAGE_TITLE:-$APP_NAME}"
APP_EMOJI="${APP_EMOJI:-}"
NOTION_PARENT_PAGE_ID="${NOTION_PARENT_PAGE_ID:-}"
TASK_DATA_SOURCE_ID="${NOTION_TASK_DATA_SOURCE_ID:-}"
BUG_DATA_SOURCE_ID="${NOTION_BUG_DATA_SOURCE_ID:-}"
TITLE_PROPERTY_ID="${NOTION_TITLE_PROPERTY_ID:-}"
ASSIGNEE_PROPERTY_NAMES_JSON_INPUT="${NOTION_ASSIGNEE_PROPERTY_NAMES_JSON:-}"
LEGACY_ASSIGNEE_PROPERTY_NAME="${NOTION_ASSIGNEE_PROPERTY_NAME:-}"
ASSIGNEE_PROPERTY_NAMES_JSON='[]'

INPUT_FILE="$DEFAULT_INPUT_FILE"
CLI_PLATFORM=""
CLI_VERSION=""
CLI_BUILD_NUMBER=""
CLI_ENVIRONMENT=""

RELEASE_PLATFORM=""
RELEASE_VERSION=""
RELEASE_BUILD_NUMBER=""
RELEASE_ENVIRONMENT=""
PUBLISHED_AT=""

FEATURE_TEXTS=()
BUG_TEXTS=()
ITEM_TYPES=()
ITEM_ORIGINAL_TEXTS=()
ITEM_LOOKUP_KEYS=()
ITEM_PAGE_IDS=()
ITEM_URLS=()
ITEM_STATUSES=()
ASSIGNEES_JSON='[]'

RESOLVED_COUNT=0
UNRESOLVED_COUNT=0
RESOLVED_PAGE_ID=""
RESOLVED_PAGE_URL=""
RESOLVED_ASSIGNEES_JSON='[]'
NOTION_RESPONSE_BODY=""
NOTION_ERROR_CODE=""
NOTION_ERROR_MESSAGE=""
LOOKUP_STATUS=""
RELEASE_PAGE_ID=""
RELEASE_PAGE_URL=""
WORK_DIR=""
NOTION_REQUEST_COUNT=0

# Print command usage.
usage() {
  printf '%s\n' \
    "Usage: fastlane/publish_notion_release.sh [options]" \
    "" \
    "Options:" \
    "  --input <path>           Release-note file (default: release_notes.txt)" \
    "  --platform <iOS|Android> Override Platform metadata" \
    "  --version <value>        Override Version metadata" \
    "  --build-number <value>   Override Build metadata" \
    "  --environment <value>    Override Environment metadata" \
    "  -h, --help               Show this help" \
    "" \
    "Environment:" \
    "  APP_NAME                 Required app name for release page content and title" \
    "  APP_EMOJI                Required release-page emoji" \
    "  NOTION_API_TOKEN         Required Notion Internal Integration token" \
    "  NOTION_PARENT_PAGE_ID    Required parent page for release pages" \
    "  NOTION_TASK_DATA_SOURCE_ID Required task data source ID" \
    "  NOTION_BUG_DATA_SOURCE_ID Required bug data source ID" \
    "  NOTION_TITLE_PROPERTY_ID Required title property ID or name" \
    "  NOTION_ASSIGNEE_PROPERTY_NAMES_JSON Ordered JSON array of people property names" \
    "  NOTION_ASSIGNEE_PROPERTY_NAME Deprecated single-property fallback" \
    "  NOTION_REQUEST_INTERVAL_MS Delay between API requests, 400-500 ms (default: 450)"
}

# Write an informational message to stderr.
log_info() {
  printf '[INFO] %s\n' "$1" >&2
}

# Write a warning message to stderr.
log_warning() {
  printf '[WARNING] %s\n' "$1" >&2
}

# Emit a structured error and terminate without exposing credentials.
emit_error() {
  local error_code="$1"
  local message="$2"
  local details="${3:-}"

  if command -v "$JQ_BIN" >/dev/null 2>&1; then
    "$JQ_BIN" -n \
      --arg code "$error_code" \
      --arg message "$message" \
      --arg details "$details" \
      '{
        success: false,
        error: {
          code: $code,
          message: $message,
          details: (if $details == "" then null else $details end)
        }
      }'
  else
    printf '[ERROR] %s: %s\n' "$error_code" "$message" >&2
  fi

  exit 1
}

# Ensure a required executable is available.
require_command() {
  local command_name="$1"
  local install_hint="$2"

  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf '[ERROR] Missing required command: %s. %s\n' \
      "$command_name" "$install_hint" >&2
    exit 127
  fi
}

# Ensure a project configuration value is available without printing its value.
require_configuration() {
  local name="$1"
  local value="$2"

  [[ -n "$value" ]] || emit_error \
    "INVALID_CONFIGURATION" "$name is required."
}

# Validate and normalize the ordered assignee property candidates.
normalize_assignee_property_names() {
  local normalized_json=""
  local legacy_property_name=""

  if [[ -n "$ASSIGNEE_PROPERTY_NAMES_JSON_INPUT" ]]; then
    if ! normalized_json="$("$JQ_BIN" -ce '
      if type == "array"
        and length > 0
        and all(.[]; type == "string" and length > 0)
      then
        reduce .[] as $name (
          [];
          if index($name) == null then . + [$name] else . end
        )
      else
        error("expected a non-empty array of non-empty strings")
      end
    ' <<< "$ASSIGNEE_PROPERTY_NAMES_JSON_INPUT" 2>/dev/null)"; then
      emit_error "INVALID_CONFIGURATION" \
        "NOTION_ASSIGNEE_PROPERTY_NAMES_JSON must be a non-empty JSON array of non-empty strings."
    fi

    ASSIGNEE_PROPERTY_NAMES_JSON="$normalized_json"
    return
  fi

  legacy_property_name="$(trim_text "$LEGACY_ASSIGNEE_PROPERTY_NAME")"
  [[ -n "$legacy_property_name" ]] || emit_error \
    "INVALID_CONFIGURATION" \
    "NOTION_ASSIGNEE_PROPERTY_NAMES_JSON is required."
  ASSIGNEE_PROPERTY_NAMES_JSON="$("$JQ_BIN" -cn \
    --arg property "$legacy_property_name" '[$property]')"
}

# Trim leading and trailing whitespace from text.
trim_text() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

# Normalize whitespace without changing visible release-note text.
normalize_whitespace() {
  printf '%s' "$1" | sed \
    -e 's/^[[:space:]]*//' \
    -e 's/[[:space:]]*$//' \
    -e 's/[[:space:]][[:space:]]*/ /g'
}

# Normalize quotes and whitespace for a Notion lookup key.
normalize_lookup_text() {
  local value
  value="$(normalize_whitespace "$1")"
  value="${value//“/\"}"
  value="${value//”/\"}"
  printf '%s' "$value"
}

# Remove a supported platform prefix from a feature title.
strip_platform_prefix() {
  local value
  local bracket_pattern='^\[(Android|iOS|App[[:space:]]+(Android|iOS))\][[:space:]]*'
  local plain_pattern='^(Android|iOS)([[:space:]]+|[[:space:]]*[-:][[:space:]]*)'

  value="$(normalize_lookup_text "$1")"
  if [[ "$value" =~ $bracket_pattern ]]; then
    value="${value:${#BASH_REMATCH[0]}}"
  elif [[ "$value" =~ $plain_pattern ]]; then
    value="${value:${#BASH_REMATCH[0]}}"
  fi

  normalize_whitespace "$value"
}

# Build the primary feature lookup key.
feature_lookup_key() {
  strip_platform_prefix "$1"
}

# Build the stable feature fallback key before the first quote.
feature_fallback_key() {
  local primary_key="$1"
  local fallback_key="$primary_key"

  if [[ "$primary_key" == *\"* ]]; then
    fallback_key="${primary_key%%\"*}"
  fi

  normalize_whitespace "$fallback_key"
}

# Extract the numeric code from a bug item.
bug_code_from_text() {
  local original_text
  local bug_pattern='\[[Bb][Uu][Gg][[:space:]]+([0-9]+)\]'

  original_text="$(normalize_lookup_text "$1")"
  if [[ "$original_text" =~ $bug_pattern ]]; then
    printf '%s' "${BASH_REMATCH[1]}"
    return 0
  fi

  return 1
}

# Extract the most specific searchable bug-title prefix from a bug item.
bug_lookup_key() {
  local original_text
  local prefix=""
  local bug_pattern='\[[Bb][Uu][Gg][[:space:]]+([0-9]+)\]'
  local prefix_pattern='^(.*\[[Bb][Uu][Gg][[:space:]]+[0-9]+\])[[:space:]]+[-:][[:space:]]+'

  original_text="$(normalize_lookup_text "$1")"
  if [[ "$original_text" =~ $prefix_pattern ]]; then
    prefix="$(trim_text "${BASH_REMATCH[1]}")"
    printf '%s' "$prefix"
    return 0
  fi

  if [[ "$original_text" =~ $bug_pattern ]]; then
    printf '[BUG %s]' "${BASH_REMATCH[1]}"
    return 0
  fi

  return 1
}

# Escape characters that can alter a Markdown link label or plain bullet.
escape_markdown_text() {
  printf '%s' "$1" | sed \
    -e 's/\\/\\\\/g' \
    -e 's/\[/\\[/g' \
    -e 's/\]/\\]/g'
}

# Parse CLI options without reading secrets from files.
parse_arguments() {
  while (($# > 0)); do
    case "$1" in
      --input)
        [[ $# -ge 2 ]] || emit_error "INVALID_ARGUMENT" "--input requires a value."
        INPUT_FILE="$2"
        shift 2
        ;;
      --platform)
        [[ $# -ge 2 ]] || emit_error "INVALID_ARGUMENT" "--platform requires a value."
        CLI_PLATFORM="$2"
        shift 2
        ;;
      --version)
        [[ $# -ge 2 ]] || emit_error "INVALID_ARGUMENT" "--version requires a value."
        CLI_VERSION="$2"
        shift 2
        ;;
      --build-number)
        [[ $# -ge 2 ]] || emit_error "INVALID_ARGUMENT" "--build-number requires a value."
        CLI_BUILD_NUMBER="$2"
        shift 2
        ;;
      --environment)
        [[ $# -ge 2 ]] || emit_error "INVALID_ARGUMENT" "--environment requires a value."
        CLI_ENVIRONMENT="$2"
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

# Read metadata and the Features/Bug Fixed sections from a UTF-8 file.
parse_release_notes() {
  local file_path="$1"
  local section=""
  local line=""
  local trimmed_line=""
  local original_text=""
  local found_features=false
  local found_bugs=false

  [[ -f "$file_path" ]] || emit_error \
    "INVALID_RELEASE_NOTE" "Release-note file not found: $file_path"

  FEATURE_TEXTS=()
  BUG_TEXTS=()
  RELEASE_PLATFORM=""
  RELEASE_VERSION=""
  RELEASE_BUILD_NUMBER=""
  RELEASE_ENVIRONMENT=""

  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    trimmed_line="$(trim_text "$line")"
    [[ -z "$trimmed_line" ]] && continue

    case "$trimmed_line" in
      "🧩 Features:"|"Features:")
        section="features"
        found_features=true
        continue
        ;;
      "🐞 Bug Fixed:"|"Bug Fixed:")
        section="bugs"
        found_bugs=true
        continue
        ;;
    esac

    if [[ -z "$section" ]]; then
      case "$trimmed_line" in
        *"Platform:"*)
          RELEASE_PLATFORM="$(trim_text "${trimmed_line##*Platform:}")"
          ;;
        *"Version:"*)
          RELEASE_VERSION="$(trim_text "${trimmed_line##*Version:}")"
          ;;
        *"Build:"*)
          RELEASE_BUILD_NUMBER="$(trim_text "${trimmed_line##*Build:}")"
          ;;
        *"Environment:"*)
          RELEASE_ENVIRONMENT="$(trim_text "${trimmed_line##*Environment:}")"
          ;;
        "- "*)
          emit_error "INVALID_RELEASE_NOTE" \
            "A bullet item appears outside Features or Bug Fixed."
          ;;
      esac
      continue
    fi

    if [[ "$trimmed_line" == *: && "$section" == "bugs" ]]; then
      section=""
      continue
    fi

    if [[ "$trimmed_line" != "- "* ]]; then
      emit_error "INVALID_RELEASE_NOTE" \
        "Every non-empty line inside a release section must start with '- '." \
        "$trimmed_line"
    fi

    original_text="${trimmed_line#- }"
    [[ -n "$original_text" ]] || emit_error \
      "INVALID_RELEASE_NOTE" "Release-note bullet text cannot be empty."

    if [[ "$section" == "features" ]]; then
      FEATURE_TEXTS[${#FEATURE_TEXTS[@]}]="$original_text"
    else
      BUG_TEXTS[${#BUG_TEXTS[@]}]="$original_text"
    fi
  done < "$file_path"

  [[ "$found_features" == true && "$found_bugs" == true ]] || emit_error \
    "INVALID_RELEASE_NOTE" "Both Features and Bug Fixed sections are required."

  if ((${#FEATURE_TEXTS[@]} + ${#BUG_TEXTS[@]} == 0)); then
    emit_error "INVALID_RELEASE_NOTE" "At least one release-note item is required."
  fi
}

# Apply CLI metadata overrides after parsing the input file.
apply_cli_overrides() {
  [[ -n "$CLI_PLATFORM" ]] && RELEASE_PLATFORM="$CLI_PLATFORM"
  [[ -n "$CLI_VERSION" ]] && RELEASE_VERSION="$CLI_VERSION"
  [[ -n "$CLI_BUILD_NUMBER" ]] && RELEASE_BUILD_NUMBER="$CLI_BUILD_NUMBER"
  [[ -n "$CLI_ENVIRONMENT" ]] && RELEASE_ENVIRONMENT="$CLI_ENVIRONMENT"
  return 0
}

# Validate and normalize release metadata before any Notion request.
validate_release_metadata() {
  local platform_lower=""
  local metadata_value=""

  for metadata_value in \
    "$RELEASE_PLATFORM" \
    "$RELEASE_VERSION" \
    "$RELEASE_BUILD_NUMBER" \
    "$RELEASE_ENVIRONMENT"; do
    if [[ -z "$metadata_value" || "$metadata_value" == *"<"* || "$metadata_value" == *">"* ]]; then
      emit_error "INVALID_RELEASE_NOTE" \
        "Platform, Version, Build, and Environment must contain real values."
    fi
  done

  platform_lower="$(printf '%s' "$RELEASE_PLATFORM" | tr '[:upper:]' '[:lower:]')"
  case "$platform_lower" in
    ios)
      RELEASE_PLATFORM="iOS"
      ;;
    android)
      RELEASE_PLATFORM="Android"
      ;;
    *)
      emit_error "INVALID_RELEASE_NOTE" "Platform must be iOS or Android."
      ;;
  esac

  [[ "$RELEASE_VERSION" =~ ^[A-Za-z0-9][A-Za-z0-9._+-]*$ ]] || emit_error \
    "INVALID_RELEASE_NOTE" "Version contains unsupported characters."
  [[ "$RELEASE_BUILD_NUMBER" =~ ^[A-Za-z0-9][A-Za-z0-9._+-]*$ ]] || emit_error \
    "INVALID_RELEASE_NOTE" "Build contains unsupported characters."
  [[ "$RELEASE_ENVIRONMENT" =~ ^[A-Za-z0-9][A-Za-z0-9._+\ -]*$ ]] || emit_error \
    "INVALID_RELEASE_NOTE" "Environment contains unsupported characters."
}

# Read an integer Retry-After header when Notion provides one.
read_retry_after() {
  local headers_file="$1"
  local line=""
  local header_name=""
  local header_value=""

  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    header_name="${line%%:*}"
    header_name="$(printf '%s' "$header_name" | tr '[:upper:]' '[:lower:]')"
    if [[ "$header_name" == "retry-after" ]]; then
      header_value="$(trim_text "${line#*:}")"
      if [[ "$header_value" =~ ^[0-9]+$ ]]; then
        printf '%s' "$header_value"
        return 0
      fi
    fi
  done < "$headers_file"

  return 1
}

# Calculate bounded exponential retry delay.
retry_delay_seconds() {
  local attempt="$1"
  local delay=$((NOTION_RETRY_BASE_SECONDS * (1 << (attempt - 1))))
  if ((delay > 30)); then
    delay=30
  fi
  printf '%s' "$delay"
}

# Return success when an HTTP status is safe to retry.
is_retryable_status() {
  case "$1" in
    429|500|503|504|529)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

# Convert the configured millisecond interval to a portable sleep value.
notion_request_interval_seconds() {
  printf '%d.%03d' \
    "$((NOTION_REQUEST_INTERVAL_MS / 1000))" \
    "$((NOTION_REQUEST_INTERVAL_MS % 1000))"
}

# Enforce one Notion API request per configured interval across all endpoints.
wait_for_notion_request_slot() {
  if ((NOTION_REQUEST_COUNT > 0)); then
    "$SLEEP_BIN" "$(notion_request_interval_seconds)"
  fi
  NOTION_REQUEST_COUNT=$((NOTION_REQUEST_COUNT + 1))
}

# POST JSON to Notion with bounded retries and optional non-fatal failures.
notion_post() {
  local endpoint="$1"
  local payload="$2"
  local default_failure_code="$3"
  local failure_mode="${4:-fatal}"
  local attempt=1
  local body_file=""
  local headers_file=""
  local http_code="000"
  local curl_exit=0
  local delay=""
  local retry_after=""
  local response_body=""
  local final_error_code="$default_failure_code"

  NOTION_RESPONSE_BODY=""
  NOTION_ERROR_CODE=""
  NOTION_ERROR_MESSAGE=""

  while ((attempt <= NOTION_MAX_ATTEMPTS)); do
    body_file="$WORK_DIR/notion-body-$attempt.json"
    headers_file="$WORK_DIR/notion-headers-$attempt.txt"
    curl_exit=0
    wait_for_notion_request_slot

    if http_code="$("$CURL_BIN" \
      --silent \
      --show-error \
      --request POST \
      --url "$NOTION_API_BASE_URL$endpoint" \
      --header "Authorization: Bearer ${NOTION_API_TOKEN_VALUE}" \
      --header "Notion-Version: ${NOTION_API_VERSION}" \
      --header "Content-Type: application/json" \
      --connect-timeout 15 \
      --max-time 60 \
      --dump-header "$headers_file" \
      --output "$body_file" \
      --write-out '%{http_code}' \
      --data-binary "$payload")"; then
      curl_exit=0
    else
      curl_exit=$?
      http_code="000"
    fi

    if ((curl_exit == 0)) && [[ "$http_code" =~ ^2[0-9][0-9]$ ]]; then
      NOTION_RESPONSE_BODY="$(<"$body_file")"
      return 0
    fi

    if ((attempt < NOTION_MAX_ATTEMPTS)) && \
      { ((curl_exit != 0)) || is_retryable_status "$http_code"; }; then
      retry_after=""
      if [[ -f "$headers_file" ]]; then
        retry_after="$(read_retry_after "$headers_file" || true)"
      fi
      delay="${retry_after:-$(retry_delay_seconds "$attempt")}"
      log_warning "Notion request failed temporarily; retrying in ${delay}s (attempt $attempt/$NOTION_MAX_ATTEMPTS)."
      "$SLEEP_BIN" "$delay"
      attempt=$((attempt + 1))
      continue
    fi

    response_body=""
    [[ -f "$body_file" ]] && response_body="$(<"$body_file")"
    response_body="${response_body:0:2000}"

    case "$http_code" in
      401|403)
        final_error_code="NOTION_UNAUTHORIZED"
        ;;
      404)
        final_error_code="NOTION_NOT_FOUND"
        ;;
      429)
        final_error_code="NOTION_RATE_LIMITED"
        ;;
      000)
        final_error_code="NOTION_REQUEST_FAILED"
        ;;
    esac

    NOTION_ERROR_CODE="$final_error_code"
    NOTION_ERROR_MESSAGE="Notion request failed with HTTP $http_code."
    if [[ "$failure_mode" == "return" ]]; then
      return 1
    fi

    emit_error "$NOTION_ERROR_CODE" "$NOTION_ERROR_MESSAGE" "$response_body"
  done
}

# Query a data source by title and expose a non-fatal lookup status.
query_data_source() {
  local data_source_id="$1"
  local lookup_key="$2"
  local payload=""
  local result_count=0
  local has_more=false
  LOOKUP_STATUS=""
  RESOLVED_PAGE_ID=""
  RESOLVED_PAGE_URL=""
  RESOLVED_ASSIGNEES_JSON='[]'

  payload="$("$JQ_BIN" -n \
    --arg property "$TITLE_PROPERTY_ID" \
    --arg lookup "$lookup_key" \
    '{
      filter: {
        property: $property,
        title: {contains: $lookup}
      },
      page_size: 2
    }')"

  if ! notion_post "/data_sources/$data_source_id/query" \
    "$payload" "NOTION_QUERY_FAILED" "return"; then
    LOOKUP_STATUS="lookup_error"
    log_warning "Task lookup failed ($NOTION_ERROR_CODE); publishing as plain text: $lookup_key"
    return 2
  fi

  if ! "$JQ_BIN" -e '.results | type == "array"' \
    >/dev/null 2>&1 <<< "$NOTION_RESPONSE_BODY"; then
    LOOKUP_STATUS="lookup_error"
    log_warning "Task lookup returned an invalid response; publishing as plain text: $lookup_key"
    return 2
  fi

  result_count="$("$JQ_BIN" -r '.results | length' <<< "$NOTION_RESPONSE_BODY")"
  has_more="$("$JQ_BIN" -r '.has_more // false' <<< "$NOTION_RESPONSE_BODY")"

  if ((result_count > 1)) || [[ "$has_more" == "true" ]]; then
    LOOKUP_STATUS="ambiguous"
    log_warning "Task lookup is ambiguous; publishing as plain text: $lookup_key"
    return 2
  fi

  if ((result_count == 0)); then
    LOOKUP_STATUS="not_found"
    return 1
  fi

  RESOLVED_PAGE_ID="$("$JQ_BIN" -r '.results[0].id // empty' \
    <<< "$NOTION_RESPONSE_BODY")"
  RESOLVED_PAGE_URL="$("$JQ_BIN" -r '.results[0].url // empty' \
    <<< "$NOTION_RESPONSE_BODY")"
  RESOLVED_ASSIGNEES_JSON="$("$JQ_BIN" -c \
    --argjson property_names "$ASSIGNEE_PROPERTY_NAMES_JSON" \
    '(
      [
        $property_names[] as $property_name
        | .results[0].properties[$property_name]?
        | select(
            .type == "people"
            and (.people | type == "array")
          )
      ]
      | first // {people: []}
    ) as $assignee_property
    | [
        $assignee_property.people[]?
        | .name?
        | select(type == "string" and length > 0)
      ]' <<< "$NOTION_RESPONSE_BODY")"

  if [[ -z "$RESOLVED_PAGE_ID" || -z "$RESOLVED_PAGE_URL" ]]; then
    LOOKUP_STATUS="lookup_error"
    RESOLVED_PAGE_ID=""
    RESOLVED_PAGE_URL=""
    RESOLVED_ASSIGNEES_JSON='[]'
    log_warning "Matched task is missing id or url; publishing as plain text: $lookup_key"
    return 2
  fi

  LOOKUP_STATUS="resolved"
  return 0
}

# Merge assigned member names while preserving their first-seen order.
merge_assignees() {
  local incoming_assignees_json="$1"

  ASSIGNEES_JSON="$("$JQ_BIN" -cn \
    --argjson current "$ASSIGNEES_JSON" \
    --argjson incoming "$incoming_assignees_json" \
    'reduce ($current + $incoming)[] as $name (
      [];
      if index($name) == null then . + [$name] else . end
    )')"
}

# Append a resolved or unresolved item to the output model.
append_result_item() {
  local item_type="$1"
  local original_text="$2"
  local lookup_key="$3"
  local page_id="$4"
  local page_url="$5"
  local status="$6"
  local assignees_json="${7:-[]}"
  local index=${#ITEM_TYPES[@]}

  ITEM_TYPES[$index]="$item_type"
  ITEM_ORIGINAL_TEXTS[$index]="$original_text"
  ITEM_LOOKUP_KEYS[$index]="$lookup_key"
  ITEM_PAGE_IDS[$index]="$page_id"
  ITEM_URLS[$index]="$page_url"
  ITEM_STATUSES[$index]="$status"

  if [[ "$status" == "resolved" ]]; then
    RESOLVED_COUNT=$((RESOLVED_COUNT + 1))
    merge_assignees "$assignees_json"
  else
    UNRESOLVED_COUNT=$((UNRESOLVED_COUNT + 1))
  fi
}

# Append one task as raw text after a non-fatal lookup failure.
append_unresolved_item() {
  local item_type="$1"
  local original_text="$2"
  local lookup_key="$3"
  local reason="${4:-unresolved}"

  log_warning "Skipping task link ($reason); publishing raw text: $original_text"
  append_result_item "$item_type" "$original_text" "$lookup_key" \
    "" "" "unresolved"
}

# Resolve every feature and bug while retaining missing tasks as plain text.
resolve_all_items() {
  local index=0
  local original_text=""
  local primary_key=""
  local fallback_key=""
  local bug_number=""

  ITEM_TYPES=()
  ITEM_ORIGINAL_TEXTS=()
  ITEM_LOOKUP_KEYS=()
  ITEM_PAGE_IDS=()
  ITEM_URLS=()
  ITEM_STATUSES=()
  ASSIGNEES_JSON='[]'
  RESOLVED_COUNT=0
  UNRESOLVED_COUNT=0

  index=0
  while ((index < ${#FEATURE_TEXTS[@]})); do
    original_text="${FEATURE_TEXTS[$index]}"
    primary_key="$(feature_lookup_key "$original_text")"
    [[ -n "$primary_key" ]] || emit_error \
      "INVALID_RELEASE_NOTE" "Feature lookup key cannot be empty."

    if query_data_source "$TASK_DATA_SOURCE_ID" "$primary_key"; then
      append_result_item "feature" "$original_text" "$primary_key" \
        "$RESOLVED_PAGE_ID" "$RESOLVED_PAGE_URL" "resolved" \
        "$RESOLVED_ASSIGNEES_JSON"
    else
      fallback_key="$primary_key"
      if [[ "$LOOKUP_STATUS" == "not_found" ]]; then
        fallback_key="$(feature_fallback_key "$primary_key")"
      fi

      if [[ "$LOOKUP_STATUS" == "not_found" && \
        "$fallback_key" != "$primary_key" ]]; then
        if query_data_source "$TASK_DATA_SOURCE_ID" "$fallback_key"; then
          append_result_item "feature" "$original_text" "$fallback_key" \
            "$RESOLVED_PAGE_ID" "$RESOLVED_PAGE_URL" "resolved" \
            "$RESOLVED_ASSIGNEES_JSON"
        else
          append_unresolved_item "feature" "$original_text" "$fallback_key" \
            "$LOOKUP_STATUS"
        fi
      else
        append_unresolved_item "feature" "$original_text" "$fallback_key" \
          "$LOOKUP_STATUS"
      fi
    fi
    index=$((index + 1))
  done

  index=0
  while ((index < ${#BUG_TEXTS[@]})); do
    original_text="${BUG_TEXTS[$index]}"
    if ! bug_number="$(bug_code_from_text "$original_text")"; then
      append_unresolved_item "bug" "$original_text" "" "invalid_lookup_key"
      index=$((index + 1))
      continue
    fi
    primary_key="$(bug_lookup_key "$original_text")"

    if query_data_source "$BUG_DATA_SOURCE_ID" "$primary_key"; then
      append_result_item "bug" "$original_text" "$primary_key" \
        "$RESOLVED_PAGE_ID" "$RESOLVED_PAGE_URL" "resolved" \
        "$RESOLVED_ASSIGNEES_JSON"
    else
      if [[ "$LOOKUP_STATUS" != "not_found" ]]; then
        append_unresolved_item "bug" "$original_text" "$primary_key" \
          "$LOOKUP_STATUS"
      else
        fallback_key="[BUG $bug_number]"
        if [[ "$fallback_key" != "$primary_key" ]] && \
          query_data_source "$BUG_DATA_SOURCE_ID" "$fallback_key"; then
          append_result_item "bug" "$original_text" "$fallback_key" \
            "$RESOLVED_PAGE_ID" "$RESOLVED_PAGE_URL" "resolved" \
            "$RESOLVED_ASSIGNEES_JSON"
        elif [[ "$LOOKUP_STATUS" != "not_found" ]]; then
          append_unresolved_item "bug" "$original_text" "$fallback_key" \
            "$LOOKUP_STATUS"
        else
          fallback_key="BUG $bug_number"
          if query_data_source "$BUG_DATA_SOURCE_ID" "$fallback_key"; then
            append_result_item "bug" "$original_text" "$fallback_key" \
              "$RESOLVED_PAGE_ID" "$RESOLVED_PAGE_URL" "resolved" \
              "$RESOLVED_ASSIGNEES_JSON"
          else
            append_unresolved_item "bug" "$original_text" "$fallback_key" \
              "$LOOKUP_STATUS"
          fi
        fi
      fi
    fi
    index=$((index + 1))
  done
}

# Render the final Notion-flavored Markdown body.
render_release_markdown() {
  local markdown=""
  local index=0
  local escaped_text=""
  local escaped_platform=""
  local escaped_environment=""
  local escaped_version=""
  local escaped_build=""

  escaped_platform="$(escape_markdown_text "$RELEASE_PLATFORM")"
  escaped_environment="$(escape_markdown_text "$RELEASE_ENVIRONMENT")"
  escaped_version="$(escape_markdown_text "$RELEASE_VERSION")"
  escaped_build="$(escape_markdown_text "$RELEASE_BUILD_NUMBER")"

  markdown="## Build information"
  markdown+=$'\n\n'
  markdown+="- **Project:** $(escape_markdown_text "$RELEASE_PAGE_TITLE")"
  markdown+=$'\n'
  markdown+="- **Platform:** $escaped_platform"
  markdown+=$'\n'
  markdown+="- **Environment:** $escaped_environment"
  markdown+=$'\n'
  markdown+="- **Version:** $escaped_version"
  markdown+=$'\n'
  markdown+="- **Build:** $escaped_build"
  markdown+=$'\n'
  markdown+="- **Published at:** $PUBLISHED_AT"
  markdown+=$'\n\n## 🧩 Features\n\n'

  index=0
  while ((index < ${#ITEM_TYPES[@]})); do
    if [[ "${ITEM_TYPES[$index]}" == "feature" ]]; then
      escaped_text="$(escape_markdown_text "${ITEM_ORIGINAL_TEXTS[$index]}")"
      if [[ "${ITEM_STATUSES[$index]}" == "resolved" ]]; then
        markdown+="- [$escaped_text](${ITEM_URLS[$index]})"
      else
        markdown+="- $escaped_text"
      fi
      markdown+=$'\n'
    fi
    index=$((index + 1))
  done

  markdown+=$'\n## 🐞 Bug Fixed\n\n'
  index=0
  while ((index < ${#ITEM_TYPES[@]})); do
    if [[ "${ITEM_TYPES[$index]}" == "bug" ]]; then
      escaped_text="$(escape_markdown_text "${ITEM_ORIGINAL_TEXTS[$index]}")"
      if [[ "${ITEM_STATUSES[$index]}" == "resolved" ]]; then
        markdown+="- [$escaped_text](${ITEM_URLS[$index]})"
      else
        markdown+="- $escaped_text"
      fi
      markdown+=$'\n'
    fi
    index=$((index + 1))
  done

  printf '%s' "$markdown"
}

# Build the release page title from reusable project configuration and metadata.
build_release_title() {
  printf '%s %s - Release %s (%s)' \
    "$RELEASE_PAGE_TITLE" \
    "$RELEASE_PLATFORM" \
    "$RELEASE_VERSION" \
    "$RELEASE_BUILD_NUMBER"
}

# Create the child release page and retain its id and internal URL.
create_release_page() {
  local title="$1"
  local markdown="$2"
  local payload=""

  payload="$("$JQ_BIN" -n \
    --arg parent_id "$NOTION_PARENT_PAGE_ID" \
    --arg title "$title" \
    --arg markdown "$markdown" \
    --arg app_emoji "$APP_EMOJI" \
    '{
      parent: {
        type: "page_id",
        page_id: $parent_id
      },
      icon: {
        type: "emoji",
        emoji: $app_emoji
      },
      properties: {
        title: {
          type: "title",
          title: [
            {
              type: "text",
              text: {content: $title}
            }
          ]
        }
      },
      markdown: $markdown
    }')"

  notion_post "/pages" "$payload" "CREATE_PAGE_FAILED"
  RELEASE_PAGE_ID="$("$JQ_BIN" -r '.id // empty' <<< "$NOTION_RESPONSE_BODY")"
  RELEASE_PAGE_URL="$("$JQ_BIN" -r '.url // empty' <<< "$NOTION_RESPONSE_BODY")"

  if [[ -z "$RELEASE_PAGE_ID" || -z "$RELEASE_PAGE_URL" ]]; then
    emit_error "CREATE_PAGE_FAILED" \
      "Create Page response is missing id or url."
  fi
}

# Emit the successful workflow result as one JSON document.
emit_success_result() {
  local items_json='[]'
  local index=0
  local item_json=""

  while ((index < ${#ITEM_TYPES[@]})); do
    item_json="$("$JQ_BIN" -cn \
      --arg source_type "${ITEM_TYPES[$index]}" \
      --arg original_text "${ITEM_ORIGINAL_TEXTS[$index]}" \
      --arg lookup_key "${ITEM_LOOKUP_KEYS[$index]}" \
      --arg page_id "${ITEM_PAGE_IDS[$index]}" \
      --arg page_url "${ITEM_URLS[$index]}" \
      --arg status "${ITEM_STATUSES[$index]}" \
      '{
        source_type: $source_type,
        original_text: $original_text,
        lookup_key: $lookup_key,
        notion_page_id: (if $page_id == "" then null else $page_id end),
        notion_url: (if $page_url == "" then null else $page_url end),
        status: $status
      }')"
    items_json="$("$JQ_BIN" -cn \
      --argjson items "$items_json" \
      --argjson item "$item_json" \
      '$items + [$item]')"
    index=$((index + 1))
  done

  "$JQ_BIN" -n \
    --arg release_page_id "$RELEASE_PAGE_ID" \
    --arg release_page_url "$RELEASE_PAGE_URL" \
    --argjson features "${#FEATURE_TEXTS[@]}" \
    --argjson bugs "${#BUG_TEXTS[@]}" \
    --argjson resolved "$RESOLVED_COUNT" \
    --argjson unresolved "$UNRESOLVED_COUNT" \
    --argjson assignees "$ASSIGNEES_JSON" \
    --argjson items "$items_json" \
    '{
      success: true,
      release_page_id: $release_page_id,
      release_page_url: $release_page_url,
      assignees: $assignees,
      summary: {
        features: $features,
        bugs: $bugs,
        resolved: $resolved,
        unresolved: $unresolved
      },
      items: $items
    }'
}

# Remove temporary HTTP artifacts.
cleanup() {
  if [[ -n "$WORK_DIR" && -d "$WORK_DIR" ]]; then
    rm -rf "$WORK_DIR"
  fi
}

# Run the complete release publishing workflow.
main() {
  local release_title=""
  local release_markdown=""

  parse_arguments "$@"
  require_command "$CURL_BIN" "Install curl in the CI image."
  require_command "$JQ_BIN" "Install jq (for example: brew install jq or apt-get install jq)."
  require_command "$SLEEP_BIN" "Install a sleep-compatible command in the CI image."

  NOTION_API_TOKEN_VALUE="${NOTION_API_TOKEN:-}"
  [[ -n "$NOTION_API_TOKEN_VALUE" ]] || emit_error \
    "NOTION_TOKEN_MISSING" "NOTION_API_TOKEN is required."
  require_configuration "APP_NAME" "$APP_NAME"
  require_configuration "APP_EMOJI" "$APP_EMOJI"
  require_configuration "NOTION_PARENT_PAGE_ID" "$NOTION_PARENT_PAGE_ID"
  require_configuration "NOTION_TASK_DATA_SOURCE_ID" "$TASK_DATA_SOURCE_ID"
  require_configuration "NOTION_BUG_DATA_SOURCE_ID" "$BUG_DATA_SOURCE_ID"
  require_configuration "NOTION_TITLE_PROPERTY_ID" "$TITLE_PROPERTY_ID"
  normalize_assignee_property_names
  [[ "$NOTION_MAX_ATTEMPTS" =~ ^[1-9][0-9]*$ ]] || emit_error \
    "INVALID_CONFIGURATION" "NOTION_MAX_ATTEMPTS must be a positive integer."
  [[ "$NOTION_RETRY_BASE_SECONDS" =~ ^[0-9]+$ ]] || emit_error \
    "INVALID_CONFIGURATION" "NOTION_RETRY_BASE_SECONDS must be a non-negative integer."
  [[ "$NOTION_REQUEST_INTERVAL_MS" =~ ^(4[0-9][0-9]|500)$ ]] || emit_error \
    "INVALID_CONFIGURATION" "NOTION_REQUEST_INTERVAL_MS must be between 400 and 500."
  RELEASE_PAGE_TITLE="$(normalize_whitespace "$RELEASE_PAGE_TITLE")"
  [[ -n "$RELEASE_PAGE_TITLE" ]] || emit_error \
    "INVALID_CONFIGURATION" "RELEASE_PAGE_TITLE cannot be empty."

  WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/plantid-notion-release.XXXXXX")"
  trap cleanup EXIT

  parse_release_notes "$INPUT_FILE"
  apply_cli_overrides
  validate_release_metadata

  PUBLISHED_AT="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  log_info "Resolving ${#FEATURE_TEXTS[@]} feature(s) and ${#BUG_TEXTS[@]} bug(s)."
  resolve_all_items

  release_title="$(build_release_title)"
  release_markdown="$(render_release_markdown)"
  create_release_page "$release_title" "$release_markdown"

  log_info "Created Notion release page: $RELEASE_PAGE_URL"
  log_info "Resolved: $RESOLVED_COUNT; unresolved plain-text items: $UNRESOLVED_COUNT."
  emit_success_result
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi

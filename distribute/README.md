# Notion Task Workflow & Agent Skill Distribution Guide

A technical reference guide for integrating Notion Task workflows with Agent Skills across multi-agent environments, Fastlane pipelines, and standalone backend/script runtimes.

**Version:** 1.0 (Updated 2026-07-30)  
**Notion API Version:** `2026-03-11`  
**Supported OS / Environments:** macOS / Linux / CI  

---

## 1. Overview

This workflow establishes Notion as a structured task source while using Agent Skills as reusable, portable playbooks. Agents read task specifications from Notion, execute code changes within target repositories, run mandatory build/test validations, and update status back to Notion in a controlled and safe manner.

### 1.1. Core Objectives

* **Standardized Task Execution:** Define a uniform flow for task retrieval, execution, validation, and status synchronization.
* **Multi-Agent Interoperability:** Maintain a single skill package shared across multiple agent platforms to prevent instruction drift.
* **Zero Secret Leakage:** Enforce strict separation of credentials from source code, logs, prompt history, and committed artifacts.
* **Flexible Runtimes:** Support Fastlane for mobile workflows while allowing standalone shell/Node/Python scripts for backend and generic projects.
* **Evidence-Based Synchronization:** Update Notion status only after required build/test checks pass with verifiable logs.

### 1.2. Standard Execution Flow

1. **Receive Input:** Agent receives task URL/ID, runtime target, and scope guidelines.
2. **Retrieve Task Data:** Agent queries the Notion Data Source using process environment tokens.
3. **Execute:** Skill routes execution to specified Fastlane lanes or script entrypoints.
4. **Validate:** Agent runs repository-required linters, unit tests, and build checks.
5. **Synchronize Results:** Upon verification success, agent updates status, proof of test, and outputs in Notion.

### 1.3. Component Responsibility Matrix

| Component | Main Responsibility | Anti-Patterns (Must Avoid) |
| :--- | :--- | :--- |
| **`SKILL.md`** | Trigger conditions, flow directives, guardrails, entrypoint routing | Hardcoded tokens, long unnecessary guides |
| **`scripts/`** | Notion API calls, payload normalization, input validation | Hardcoded secrets, user shell profile dependencies |
| **`Fastfile`** | Lane orchestration, env verification, argument passing | Real tokens, hardcoded database/data source IDs |
| **`Notion`** | Task source, status tracking, acceptance criteria, test evidence links | Credentials, private access tokens, sensitive logs |
| **CI Secret Store** | Injecting runtime environment variables | Committing secrets into source repositories |

> [!CAUTION]
> **Security Guardrail:** Tokens must reside exclusively within environment variables or runtime secret managers. Never paste tokens into prompts, issues, logs, screenshots, or committed files.

---

## 2. Multi-Agent Skill Setup & Installation

Agent Skills are organized into folders containing a primary `SKILL.md` file along with optional `scripts/`, `references/`, and `assets/`. Using `.agents/skills` as the repository-level standard path provides optimal cross-agent compatibility.

### 2.1. Skill Directory Structure

```text
.agents/skills/distribute/
├── SKILL.md
├── scripts/
│   └── run.sh
├── references/
│   └── notion-schema.md
└── assets/
    └── payload-template.json
```

* **Requirement:** `SKILL.md` must contain standard YAML frontmatter with `name` and `description`. The `description` acts as the trigger signal for agent activation.

### 2.2. Cross-Agent Compatibility Matrix

| AI Agent / IDE | Project-Level Location | User-Level Location | Recommendation |
| :--- | :--- | :--- | :--- |
| **OpenAI Codex** | `.agents/skills/` | `~/.agents/skills/` | Native `.agents/skills` support |
| **Google Antigravity IDE** | `.agents/skills/` | `~/.gemini/config/skills/` | Project standard source |
| **Gemini CLI** | `.agents/skills/` or `.gemini/skills/` | `~/.agents/skills/` | Prefer `.agents/skills` |
| **GitHub Copilot** | `.agents/skills/`, `.github/skills/` | `~/.agents/skills/` | Prefer `.agents/skills` |
| **Cursor** | `.agents/skills/` or `.cursor/skills/` | `~/.cursor/skills/` | Prefer `.agents/skills` |
| **Claude Code** | `.claude/skills/` | `~/.claude/skills/` | Create symlink to `.agents/skills` |

Agents fall into two operational categories:
* **Group A (Direct `.agents/skills` readers):** OpenAI Codex, Google Antigravity IDE, Gemini CLI, GitHub Copilot, Cursor.
* **Group B (Requires custom path / symlink):** Claude Code.

### 2.3. Project-Level Installation (Recommended)

To install the skill within a specific repository:

```bash
mkdir -p .agents/skills/distribute
cp -R PATH_TO_SKILL_PACKAGE/. .agents/skills/distribute/
test -f .agents/skills/distribute/SKILL.md
```

For **Claude Code**, link `.claude/skills` to `.agents/skills`:

```bash
mkdir -p .claude/skills
ln -s "../../.agents/skills/distribute" .claude/skills/distribute
```

*(Note: On Windows or environments without symlink support, copy the directory and maintain synchronized copies.)*

### 2.4. User-Level Installation

For global availability across all user repositories:

```bash
mkdir -p ~/.agents/skills
cp -R PATH_TO_SKILL_PACKAGE ~/.agents/skills/distribute
```

> [!NOTE]
> Do not store project-specific schemas inside user-level skills to prevent accidental cross-workspace operations.

### 2.5. Post-Installation Verification Prompt

Test if the agent successfully discovers and registers the skill without executing commands:

```text
Please inspect the skill `distribute` in this workspace.
Read metadata only and list:
1) Discovered SKILL.md path;
2) Trigger conditions;
3) Permitted script entrypoints;
4) Required environment variables.
Do NOT run scripts, and do NOT read or display environment variable values.
```

---

## 3. Environment Variable Configuration

The workflow requires two mandatory environment variables and one recommended API version header.

| Variable Name | Required | Description |
| :--- | :--- | :--- |
| `NOTION_API_TOKEN` | **Yes** | Internal Integration Secret (passed via `Authorization: Bearer` header). |
| `NOTION_TASK_DATA_SOURCE_ID` | **Yes** | Notion Data Source ID containing task records (not database container ID). |
| `NOTION_API_VERSION` | *Optional* | API version header (`Notion-Version`). Default: `2026-03-11`. |

### 3.1. Retrieving & Testing `NOTION_API_TOKEN`

1. Navigate to Notion Integrations portal and create an Internal Integration (e.g., `Task Automation - Development`).
2. Grant **Read content** permissions (and **Insert/Update content** only if status synchronization is required).
3. Copy the Internal Integration Secret.
4. Open the target Tasks database in Notion → `•••` menu → **Add connections** → Select your integration.
5. Store the token in your local `.env` file (ensure it is gitignored) or secret store.

Validate the token using `curl` (without printing secrets):

```bash
export NOTION_API_TOKEN='PASTE_TOKEN_IN_CURRENT_SHELL'
export NOTION_API_VERSION='2026-03-11'

curl --fail-with-body --silent --show-error \
  https://api.notion.com/v1/users/me \
  -H "Authorization: Bearer ${NOTION_API_TOKEN}" \
  -H "Notion-Version: ${NOTION_API_VERSION}"
```

* **Expected Output:** HTTP 200 with bot payload JSON. (HTTP 401 indicates an invalid or revoked token).

### 3.2. Retrieving `NOTION_TASK_DATA_SOURCE_ID`

Starting from Notion API `2025-09-03` and `2026-03-11`, databases act as containers that house data sources. Query endpoints require `data_source_id`.

#### Option A: Direct Copy via Notion UI
1. Open the Tasks database in Notion.
2. Database Settings (`•••`) → **Manage data sources**.
3. Select **Copy data source ID**.

#### Option B: API Retrieval via Database ID
If you have the Database Container ID (the 32-character string in the database URL):

```bash
export NOTION_DATABASE_ID='PASTE_DATABASE_CONTAINER_ID'

curl --fail-with-body --silent --show-error \
  "https://api.notion.com/v1/databases/${NOTION_DATABASE_ID}" \
  -H "Authorization: Bearer ${NOTION_API_TOKEN}" \
  -H "Notion-Version: ${NOTION_API_VERSION}" \
  | jq '.data_sources[] | {id, name}'
```

#### Option C: Search API
Search for accessible data sources matching the database title:

```bash
curl --fail-with-body --silent --show-error \
  -X POST https://api.notion.com/v1/search \
  -H "Authorization: Bearer ${NOTION_API_TOKEN}" \
  -H "Notion-Version: ${NOTION_API_VERSION}" \
  -H "Content-Type: application/json" \
  --data '{"query":"Tasks","filter":{"property":"object","value":"data_source"}}' \
  | jq '.results[] | {id, object, url}'
```

### 3.3. API Connection Troubleshooting Reference

| HTTP Code | Common Cause | Resolution |
| :---: | :--- | :--- |
| **200** | Request successful | Proceed with schema verification. |
| **400** | Malformed ID, invalid payload, or wrong API version | Check `data_source_id` format and JSON structure. |
| **401** | Invalid or revoked token | Rotate token and update local environment/secret store. |
| **403** | Missing integration capabilities | Grant Read/Update permissions under integration settings. |
| **404** | Database not shared or incorrect ID | Re-check **Add connections** on the database page. |
| **429** | Rate limit exceeded | Implement exponential backoff with jitter. |

### 3.4. Fastlane Environment Integration

For Fastlane projects, store secrets in `fastlane/.env` and commit a empty template as `fastlane/.env.example`.

* **`fastlane/.env.example`** *(Committed to Git)*:
  ```ini
  NOTION_API_TOKEN=
  NOTION_TASK_DATA_SOURCE_ID=
  NOTION_API_VERSION=2026-03-11
  ```

* **`fastlane/.env`** *(Local/CI only, Gitignored)*:
  ```ini
  NOTION_API_TOKEN=secret_real_token_here
  NOTION_TASK_DATA_SOURCE_ID=data_source_id_here
  NOTION_API_VERSION=2026-03-11
  ```

* **`.gitignore`**:
  ```gitignore
  fastlane/.env
  fastlane/.env.*
  !fastlane/.env.example
  ```

* **Fail-Fast Validation in `fastlane/Fastfile`**:
  ```ruby
  before_all do
    ensure_env_vars(
      env_vars: %w[
        NOTION_API_TOKEN
        NOTION_TASK_DATA_SOURCE_ID
      ]
    )
  end
  ```

Run lane using environment files:
```bash
bundle exec fastlane notion_task task_id:"PASTE_NOTION_PAGE_ID_OR_URL" --env local
```

### 3.5. Standalone Runtime Options (Non-Fastlane)

* **Shell Environment:** Export variables in current session (`export NOTION_API_TOKEN=...`).
* **Dotenv Runners:** Use `dotenvx`, `direnv`, Node `--env-file`, or `python-dotenv`:
  ```bash
  # Node.js 20+
  node --env-file=.env.local .agents/skills/distribute/scripts/run.sh

  # Python
  python -m dotenv -f .env.local run -- python .agents/skills/distribute/scripts/run.sh
  ```
* **Secret Managers:** GitHub Actions Secrets, AWS Secrets Manager, GCP Secret Manager, 1Password CLI.

---

## 4. Usage Guidelines & Prompts

### 4.1. Pre-Run Checklist

- [ ] Skill detected by active agent system and trigger description matches prompt.
- [ ] Valid `NOTION_API_TOKEN` and database connection active via **Add connections**.
- [ ] Verified `NOTION_TASK_DATA_SOURCE_ID` via query/retrieve.
- [ ] Secrets added to `.gitignore` and absent from git status.
- [ ] Repository test/lint/build verification commands identified.

---

### 4.2. One-Time Fastlane Integration Prompt Template

Use this prompt when integrating the Notion task lane into a project's existing `Fastfile`:

```text
Use the skill `distribute` in this repository to integrate the Notion Task workflow into Fastlane.

Requirements:
1. Read SKILL.md and required references/scripts only. Never read or print values from `.env` files.
2. Inspect `fastlane/Fastfile`, Gemfile, and existing lanes before editing.
3. Perform minimal changes:
   - Add or reuse the `notion_task` lane;
   - Enforce `ensure_env_vars` for `NOTION_API_TOKEN` and `NOTION_TASK_DATA_SOURCE_ID`;
   - Retrieve secrets via `ENV.fetch`, never hardcoding or logging tokens;
   - Accept `task_id`/URL and `dry_run` options;
   - Call the declared entrypoint script;
   - Pass exit codes and sanitized error messages back to Fastlane.
4. Create/update `fastlane/.env.example` with empty variable keys; ensure `fastlane/.env*` is gitignored while keeping `.env.example`.
5. Do not invent property names or status values. If missing, report exact schema requirements.
6. Run syntax checks and tests. Do NOT update Notion during integration; use dry-run mode.
7. Finish with a summary of modified files, executed test commands, and safe Fastlane invocation examples.
```

---

### 4.3. Runtime Fastlane Task Execution Prompt Template

Use this prompt to execute a specific Notion task via Fastlane:

```text
Use the skill `distribute` to process the following Notion task:
- Task URL/ID: PASTE_NOTION_PAGE_ID_OR_URL
- Fastlane environment: local
- Mode: Dry-run first, execute only upon dry-run validation.

Mandatory Flow:
1. Do NOT read `.env` contents and do NOT log secrets; verify required variable existence only.
2. Confirm the task belongs to `NOTION_TASK_DATA_SOURCE_ID`, read acceptance criteria and dependencies.
3. Verify `notion_task` lane exists in Fastfile. If missing, stop and error out.
4. Run:
   bundle exec fastlane notion_task task_id:"PASTE_NOTION_PAGE_ID_OR_URL" --env local
5. Edit files only within task scope. Validate inputs and sanitize values passed to shell commands.
6. Execute mandatory repository lint/test/build checks.
7. Update status/results in Notion ONLY after all checks pass. If write permissions are absent, print proposed update payload for user review.
8. Provide a concise summary: modified files, test outputs, Notion status, and remaining blockers.
```

---

### 4.4. Standalone (Non-Fastlane) Task Execution Prompt Template

Use this prompt for Backend, Web, or CLI projects without Fastlane:

```text
Use the skill `distribute` to process a Notion task in this repository without Fastlane.

Inputs:
- Task URL/ID: PASTE_NOTION_PAGE_ID_OR_URL
- Runtime: PASTE_NODE_PYTHON_RUBY_OR_SHELL
- Environment source: Process environment injected via shell/CI/secret manager.

Requirements:
1. Read SKILL.md to determine the exact script entrypoint. Reuse existing scripts.
2. Do NOT read `.env` files, display secrets, or pass tokens as CLI arguments. Access `NOTION_API_TOKEN`, `NOTION_TASK_DATA_SOURCE_ID`, and `NOTION_API_VERSION` strictly from `process.env` / `ENV`.
3. Validate task ID/URL, data source ID, and all command parameters.
4. Run entrypoint in dry-run mode first.
5. Execute minimal code changes strictly adhering to task acceptance criteria.
6. Run repository linters, unit tests, and build checks.
7. Synchronize results to Notion only after validation succeeds. Keep original task status intact if execution fails.
8. Report modified files, executed test commands, test results, and sync status.
```

---

### 4.5. Direct Script Invocation Example

When calling entrypoint scripts directly in terminal or CI:

```bash
export NOTION_TASK_PAGE_ID='PASTE_NOTION_PAGE_ID'

# Call entrypoint via environment variable to prevent logging tokens in process trees
SCRIPT_ENTRYPOINT --task-id "${NOTION_TASK_PAGE_ID}" --dry-run
```

---

### 4.6. Definition of Done (Completion Criteria)

- [x] Agent utilizes declared skill entrypoints without constructing parallel unvetted flows.
- [x] Zero credentials or tokens present in git diffs, logs, artifacts, or prompt history.
- [x] Input from Notion is validated and sanitized before invocation.
- [x] Repository lint, build, and test steps executed with clean pass results.
- [x] Notion task status updated only upon empirical proof of build/test success.

---

## 5. Official Documentation & References

* [OpenAI Codex — Skills & Customization](https://platform.openai.com)
* [Google Antigravity — Agent Skills Documentation](https://antigravity.google)
* [Gemini CLI — Agent Skills Reference](https://gemini.google)
* [GitHub Copilot — Agent Skills Guide](https://docs.github.com/copilot)
* [Claude Code — Extend Claude with Skills](https://docs.anthropic.com/claude-code)
* [Cursor — Agent Skills Specification](https://cursor.com)
* [Notion API — Authorization](https://developers.notion.com/docs/authorization)
* [Notion API — Retrieve a Database](https://developers.notion.com/reference/retrieve-a-database)
* [Notion API — Retrieve a Data Source](https://developers.notion.com/reference/retrieve-a-data-source)
* [Notion API — Query a Data Source](https://developers.notion.com/reference/query-a-data-source)
* [Fastlane — Environment Variables](https://docs.fastlane.tools/advanced/other/#environment-variables)
* [Fastlane — `ensure_env_vars` Action](https://docs.fastlane.tools/actions/ensure_env_vars/)

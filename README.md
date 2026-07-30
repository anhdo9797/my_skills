# My Skills Repository

A curated collection of custom **AI Agent Skills** designed for cross-agent compatibility (Google Antigravity IDE, OpenAI Codex, Claude Code, Cursor, GitHub Copilot, and Gemini CLI).

This repository provides reusable, portable skill packages and workflow guides to automate QA testing, task synchronization, and multi-agent skill distribution.

---

## 📁 Repository Overview

```text
my_skills/
├── distribute/              # Notion Task Workflow & Skill Distribution Skill
│   ├── SKILL.md             # Skill entrypoint & trigger definitions
│   ├── README.md            # Detailed distribution & Notion integration guide
│   ├── agents/              # Custom agent configurations
│   ├── assets/              # Payload templates
│   └── references/          # Configuration, Fastlane, and validation guides
├── maestro-test-executor/   # Maestro Mobile UI Test Execution Skill
│   ├── SKILL.md             # Skill entrypoint for automated mobile E2E testing
│   ├── DOC.md               # Detailed technical documentation
│   ├── scripts/             # Hierarchy filtering and screenshot comparison tools
│   └── references/          # Maestro commands, YAML flows, inspection, and reporting
├── docs/                    # Reference specifications & source documents
└── README.md                # Root repository documentation
```

---

## 🚀 Available Skills

### 1. `distribute` — Notion Task Workflow & Agent Skill Distribution
* **Path:** [`distribute/`](distribute/)
* **Skill Entrypoint:** [`distribute/SKILL.md`](distribute/SKILL.md)
* **Detailed Guide:** [`distribute/README.md`](distribute/README.md)

**Description:**
Establishes Notion as a structured task management source while enabling seamless distribution of agent skills across multi-agent environments. Standardizes skill directory layout (`.agents/skills`), enforces zero-secret security guardrails, and provides Fastlane / standalone script integration for CI/CD pipelines.

**Key Features:**
* Standardized `.agents/skills/` distribution format compatible with major AI agents.
* Automated Notion task fetching, status updates, and test evidence attachments.
* Fastlane and standalone shell/script execution support.
* Strict credential isolation avoiding token leaks in prompt history or committed files.

---

### 2. `maestro-test-executor` — Maestro Mobile UI Test Execution
* **Path:** [`maestro-test-executor/`](maestro-test-executor/)
* **Skill Entrypoint:** [`maestro-test-executor/SKILL.md`](maestro-test-executor/SKILL.md)
* **Detailed Documentation:** [`maestro-test-executor/DOC.md`](maestro-test-executor/DOC.md)

**Description:**
Automates mobile QA testing by converting test plans into executable [Maestro](https://maestro.mobile.dev/) YAML flows. Designed for non-technical testers without requiring source code reading. Runs flows incrementally, inspects live screen hierarchies efficiently, optionally compares UI screenshots against Figma baselines, and generates consolidated markdown test reports.

**Key Features:**
* Direct translation of manual QA test cases into Maestro `.yaml` flows.
* Context-efficient screen inspection using [`scripts/filter_hierarchy.py`](maestro-test-executor/scripts/filter_hierarchy.py).
* Visual UI verification and image diffing via [`scripts/compare_screenshots.py`](maestro-test-executor/scripts/compare_screenshots.py).
* Living `report.md` resume/upsert mechanism across multi-session test executions.

---

## 🛠️ Installation & Setup

Skills can be installed at the **Project Level** (per repository) or **Global Level** (user profile).

### 1. Cross-Agent Compatibility Matrix

| AI Agent / IDE | Project Path | Global / User Path | Recommended Strategy |
| :--- | :--- | :--- | :--- |
| **Google Antigravity IDE** | `.agents/skills/` | `~/.gemini/config/skills/` | Project or Global config |
| **OpenAI Codex** | `.agents/skills/` | `~/.agents/skills/` | Native `.agents/skills/` |
| **Gemini CLI** | `.agents/skills/` | `~/.agents/skills/` | Native `.agents/skills/` |
| **GitHub Copilot** | `.agents/skills/` | `~/.agents/skills/` | Native `.agents/skills/` |
| **Cursor** | `.agents/skills/` | `~/.cursor/skills/` | Native `.agents/skills/` |
| **Claude Code** | `.claude/skills/` | `~/.claude/skills/` | Symlink to `.agents/skills/` |

### 2. Installing a Skill into a Project

To add a skill (e.g., `distribute` or `maestro-test-executor`) to your workspace:

```bash
# Create target directory
mkdir -p .agents/skills/<skill-name>

# Copy skill files from this repository
cp -R path/to/my_skills/<skill-name>/. .agents/skills/<skill-name>/
```

For **Claude Code** support, create a symlink pointing to `.agents/skills`:

```bash
mkdir -p .claude/skills
ln -s "../../.agents/skills/<skill-name>" .claude/skills/<skill-name>
```

### 3. Installing Skills Globally (User Scope)

To make a skill available across all your projects on macOS/Linux:

* **Google Antigravity IDE:**
  ```bash
  cp -R distribute ~/.gemini/config/skills/distribute
  cp -R maestro-test-executor ~/.gemini/config/skills/maestro-test-executor
  ```

* **General Agents (`.agents/skills`):**
  ```bash
  cp -R distribute ~/.agents/skills/distribute
  cp -R maestro-test-executor ~/.agents/skills/maestro-test-executor
  ```

---

## 🔒 Security Best Practices

1. **Environment Variables Only:** Never hardcode credentials, tokens, or API keys in `SKILL.md`, scripts, or test flows. Use `.env` files or environment variables.
2. **Ignored Secrets:** Ensure `.env` and sensitive runtime assets are included in `.gitignore`.
3. **Log Protection:** Sanitize logs before attaching them to test reports or Notion updates.

---

## 📝 License

This repository is maintained for internal tool and skill distribution.

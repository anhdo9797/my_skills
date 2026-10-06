# My Skills Repository

A curated collection of custom **AI Agent Skills** designed for cross-agent compatibility (Google Antigravity IDE, OpenAI Codex, Claude Code, Cursor, GitHub Copilot, and Gemini CLI).

This repository provides reusable, portable skill packages and workflow guides to automate QA testing, task synchronization, and multi-agent skill distribution.

---

## 📁 Repository Overview

```text
my_skills/
├── app-idea-researcher/     # App Market Research & Idea Scoring Skill
│   ├── SKILL.md             # Research workflow: data check → discovery → analysis → scoring → report
│   ├── references/          # Phase methodologies, data-source discovery, dated benchmarks, report template
│   ├── scripts/             # Public store lookup + weighted scoring/verdict calculator
│   └── evals/               # Eval prompts and registry fixture
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
├── review-bitbucket-pr/     # Bitbucket Pull Request Review Skill
│   ├── SKILL.md             # Review workflow, modes, and stack selection
│   ├── references/          # Review contract + per-stack detector profiles
│   ├── scripts/             # Bitbucket Cloud/Server PR URL parser
│   └── evals/               # Eval prompts and mock connector fixtures
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
Automates mobile QA testing by converting test plans into executable [Maestro](https://maestro.mobile.dev/) YAML flows. Designed for non-technical testers without requiring source code reading. Runs flows incrementally, inspects live screen hierarchies efficiently, validates how each screen looks — against a Figma design or from the screenshot alone — and generates consolidated markdown test reports.

**Key Features:**
* Direct translation of manual QA test cases into Maestro `.yaml` flows.
* Context-efficient screen inspection using [`scripts/filter_hierarchy.py`](maestro-test-executor/scripts/filter_hierarchy.py).
* Three-tier UI validation: Maestro assertions and pixel-diff baselines run unattended in CI ([`scripts/compare_screenshots.py`](maestro-test-executor/scripts/compare_screenshots.py)), while an on-demand **visual review** grids the screenshot ([`scripts/grid_overlay.py`](maestro-test-executor/scripts/grid_overlay.py)) and scans it cell-by-cell for clipping, overlap, and misalignment — auto-failing on serious defects and returning an annotated image that marks exactly which cells are wrong.
* Living `report.md` resume/upsert mechanism across multi-session test executions.


### 3. `review-bitbucket-pr` — Bitbucket Pull Request Review
* **Path:** [`review-bitbucket-pr/`](review-bitbucket-pr/)
* **Skill Entrypoint:** [`review-bitbucket-pr/SKILL.md`](review-bitbucket-pr/SKILL.md)
* **Review Contract:** [`review-bitbucket-pr/references/review-contract.md`](review-bitbucket-pr/references/review-contract.md)

**Description:**
Reviews a pull request on any Bitbucket Cloud or Bitbucket Server repository. Fetches the diff through a Bitbucket MCP connector, validates every candidate finding against the repository's own conventions and reachable code paths, posts evidence-backed inline comments in Vietnamese, and returns a severity summary with a merge recommendation. Never approves, merges, or edits code.

**Key Features:**
* **Live and dry-run modes** — dry run replays a local diff, patch, or fixture with no connector and posts nothing, so a review can be previewed or tested offline.
* **Stack profiles** — universal quality gates in the review contract, with per-ecosystem detectors in [`references/stacks/`](review-bitbucket-pr/references/stacks/); [`deriving-a-profile.md`](review-bitbucket-pr/references/stacks/deriving-a-profile.md) covers repositories with no written profile.
* **Three coverage gates** — user-facing copy, complexity, and compatibility, tracked per changed hunk so no hunk is silently skipped.
* **Deterministic URL parsing** via [`scripts/parse_pr_url.py`](review-bitbucket-pr/scripts/parse_pr_url.py), which rejects GitHub/GitLab URLs instead of misreading them.
* Evidence threshold and deduplication rules that suppress style noise and findings an existing unresolved comment already covers.

---

### 4. `app-idea-researcher` — App Market Research & Idea Scoring
* **Path:** [`app-idea-researcher/`](app-idea-researcher/)
* **Skill Entrypoint:** [`app-idea-researcher/SKILL.md`](app-idea-researcher/SKILL.md)
* **Report Template:** [`app-idea-researcher/references/report_template.md`](app-idea-researcher/references/report_template.md)

**Description:**
Acts as a Product Owner to find, analyze and rank mobile app ideas for a given team. Discovers niches, analyzes competitors with real store data, builds a USP, scores feasibility, and writes a decision report in the user's language — every idea with a verdict, a confidence level and the cheapest validation step.

**Key Features:**
* **Vendor-neutral data discovery** — finds whatever store-data / ASO tools the session has by capability, probes each once, and classifies plan-locked, transient and silently-null responses ([`references/data_sources.md`](app-idea-researcher/references/data_sources.md)). Never reads MCP config or credentials; with no tools connected it falls back to public store data.
* **Public store lookup** via [`scripts/store_lookup.py`](app-idea-researcher/scripts/store_lookup.py) — Google Play installs/rating/updated/ads/IAP and App Store ratings, standard library only.
* **Deterministic scoring** via [`scripts/score.py`](app-idea-researcher/scripts/score.py) — weighted score, one set of verdict bands with hard gates, per-criterion confidence, and downside/scenario sensitivity.
* **Dated, sourced benchmarks** for subscription funnels, eCPM, CPI, store fees and Vietnam team cost ([`references/benchmarks.md`](app-idea-researcher/references/benchmarks.md)).
* **Idea registry** (`ideas_registry.md` next to the reports) so later runs reuse and re-score earlier ideas instead of starting over.

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

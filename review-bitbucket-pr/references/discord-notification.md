# Discord notification after a live review (optional, self-onboarding)

Run this only after a **live** review has finished. Dry runs never notify. The integration lives in the *reviewed project*, is discovered dynamically each session, and is set up once with the user's consent; after that it runs with no questions.

Hard rules, always:

- Never open, print, or inspect dotenv files, webhook values, or secrets. Never put a webhook in arguments, JSON, logs, or chat. Pass only the env-file *path* and let the script read it.
- Notification failure never changes the review result. Report it in one line and move on; do not retry in a loop.
- Send exactly one notification per review.

## 1. Discover (every session, in this order)

Work from the repository root of the checkout you are reviewing (read-only; never switch branches).

1. **Recorded integration.** Read the nearest `AGENTS.md`, else `CLAUDE.md`, and look for the block delimited by `<!-- review-bitbucket-pr:discord -->` … `<!-- /review-bitbucket-pr:discord -->` (format in §5).
   - Block found, `mode: script`, and the `script:` path exists → go to §3 and **send without asking anything**.
   - Block found, `mode: ci` → the pipeline sends it. Do not send; report `Discord: do CI/CD gửi`.
   - Block found, `mode: off` → skip; report `Discord: đã tắt trong cấu hình dự án`.
   - Block found but the script path is missing → say the recorded script is gone and offer re-onboarding (§2). Do not guess a path.
2. **Unrecorded but present.** No block. Look for an existing sender: `git ls-files` filtered by `*discord*notif*`, `*review*notif*`, `*notify*review*` across any folder (`scripts/`, `tools/`, `fastlane/`, `ci/`, `.github/`, `bin/`). Also check CI config for a Discord step: `bitbucket-pipelines.yml`, `.github/workflows/*`, `.gitlab-ci.yml`, `Jenkinsfile`, `fastlane/Fastfile`, `Makefile`. If a compatible script (accepts `--pr-url` and `--review-json`) exists, confirm its path with the user once, then record it (§5). If only a CI step exists, ask whether CI should own notifications (`mode: ci`).
3. **Nothing found** → onboarding (§2), unless the user said not to notify; then skip with `Discord: chưa tích hợp`.

If the user says "không gửi discord" / "skip notify" for this run, skip regardless of the record.

## 2. Onboarding (only when nothing is integrated)

Ask, in Vietnamese, in this order. Keep each question short and offer a default found from the repo.

1. **Muốn tích hợp thông báo Discord sau mỗi review không?** If no → write `mode: off` to the instruction file only if the user wants it remembered; otherwise just skip.
2. **Cách tích hợp:** script do agent chạy sau review (`script`, default) hay do CI/CD gửi (`ci`)? For `ci`, offer to add a step to the existing pipeline file but do not invent pipeline syntax for tools you have not seen in the repo; show the proposed diff first.
3. **Thư mục đặt script:** suggest from what exists (`scripts/`, `tools/`, `fastlane/`, `bin/`, `ci/` — pick the one the repo already uses for shell scripts; if none, suggest `scripts/`). File name: `send_discord_review_notification.sh`.
4. **Nguồn webhook (`DISCORD_WEBHOOK_REVIEW_CHANNEL`):** offer, in this order:
   - biến môi trường export sẵn, hoặc block `env` trong `~/.claude/settings.json` (nothing to record in the repo);
   - file env cấp user, ví dụ `~/.config/review-bitbucket-pr/discord.env` (recommended: outside the repo);
   - file env trong dự án (e.g. `.env`) — only if it is gitignored; check with `git check-ignore <path>`, and if not ignored, warn and recommend another location.
   Ask for the **path only**, never the value. If the user wants help creating the file, tell them the single line to add (`DISCORD_WEBHOOK_REVIEW_CHANNEL=<webhook>`) and let them paste the secret themselves; remind them to `chmod 600` it.

Then integrate automatically:

- Copy the bundled `scripts/send_discord_review_notification.sh` (next to this skill's `SKILL.md`) to the chosen folder, keep it executable (`chmod +x`), and do not modify it. It needs `bash`, `curl`, `jq` — check with `command -v` and tell the user if one is missing.
- If the env source is a file, record its path so it can be passed as `--env-file` (§3).
- Add the script to version control only if the user agrees; otherwise leave it untracked and say so.

## 3. Test (ask first)

Ask: **Chạy thử không?** Offer two levels:

1. **Kiểm tra payload (không gửi, không cần webhook):**
   ```bash
   <script> --print-payload --pr-url "https://bitbucket.org/example/test/pull-requests/1" \
     --review-json '{"decision":"approve","inline_comments":0,"findings":[]}'
   ```
   Expect a JSON embed on stdout.
2. **Gửi thử thật lên kênh Discord** (needs explicit consent because it posts to a real channel). Use a clearly labelled fake PR URL and a finding titled `Tin nhắn kiểm tra tích hợp — bỏ qua`, with `decision` `approve_with_suggestions` and a single `suggestion`.

Report the outcome. If the test fails, show the script's error line (it never contains the webhook), fix what is fixable (path, executable bit, missing tool, wrong env-file path), and offer to retry once. Do **not** write the record (§5) until the user is satisfied or explicitly chooses to keep it anyway.

## 4. Send after a review

### Gate — all must hold, otherwise do not send and state the reason

1. Live mode, review completed with **full coverage** (not "40 of 120 files").
2. The reviewed head is still the current source head; if it moved, refresh, revalidate findings, then continue.
3. All PR metadata and comment queries succeeded, following every pagination cursor/next link.
4. A canonical HTTPS PR URL is available from the connector.

### Collect

- One record per **validated, distinct** finding from this review. Include an existing unresolved finding only if revalidated against the current head. Exclude resolved, deleted, obsolete, unrelated, and unverified comments.
- `inline_comments` = unique count of **successfully posted new top-level inline comments** from this review (confirm by the write response; if it lacks details, query the comment by ID). Exclude replies, general comments, old comments, and failed writes.
- Keep findings in `findings` even when posting failed or an existing thread prevented a duplicate; severity totals may exceed `inline_comments`. Do not infer either number from the PR's total comment count.

### Map to JSON

| Review data | JSON |
| --- | --- |
| Final recommendation `Request changes` / `Need clarification` / `Approve with suggestions` / `Approve` | `decision`: `changes_requested` / `need_clarification` / `approve_with_suggestions` / `approve` |
| Severity marker `[Blocker]`…`[Question]` | `severity`, lowercase |
| Comment first-line title | `title`: marker and Markdown stripped, Vietnamese, one line, ideally 60–100 chars, no evidence/code/fix |
| Successful new inline comments | `inline_comments` (non-negative integer) |

Consistency the script enforces: any Blocker/Major ⇒ `changes_requested`; no findings ⇒ `approve`; an unresolved Question ⇒ `need_clarification` or `changes_requested`; Suggestion/Minor only ⇒ not `approve`. Do not promote Suggestion or Question to Minor. Send the **full** finding list (up to 10,000); never truncate it, and never send manual counts or colors — the script computes them.

Build the JSON with a structured tool argument or `jq --arg/--argjson`; never interpolate raw comment text into shell code. A clean review is `{"decision":"approve","inline_comments":0,"findings":[]}`.

### Invoke directly (one call)

```bash
<script-path-from-record> \
  --pr-url "<canonical https PR url>" \
  --review-json '<json>' \
  [--env-file "<path-from-record>"]
```

Call the script itself, not through a wrapper that expands the environment. If the user's shell proxies commands (for example `rtk proxy`), use whatever prefix the project record specifies. If the script reports missing configuration, report `Discord: chưa cấu hình webhook` and stop.

### Report (one line in the result's Kết luận)

`Discord: đã gửi` · `Discord: bỏ qua (<lý do>)` · `Discord: chưa tích hợp` · `Discord: do CI/CD gửi` · `Discord: gửi thất bại (<lý do ngắn>)`

## 5. Record the integration (after a successful test or explicit user choice)

Write a short block to `AGENTS.md` if it exists, else `CLAUDE.md`; if both or neither exist, ask which to use. Update the block in place if it already exists; never duplicate it. Contain **no secrets** — only paths and the variable *name*.

```markdown
<!-- review-bitbucket-pr:discord -->
## Review notifications (Discord)

- mode: script            # script | ci | off
- script: scripts/send_discord_review_notification.sh
- env-file: ~/.config/review-bitbucket-pr/discord.env   # omit when the webhook is exported / set in Claude Code settings
- variable: DISCORD_WEBHOOK_REVIEW_CHANNEL
- command-prefix:         # optional, e.g. `rtk proxy`
- after a live PR review (never on dry run) the agent sends one notification automatically using the skill's JSON contract; do not ask again.
<!-- /review-bitbucket-pr:discord -->
```

Per the project's documentation rules, update the instruction file and add no extra report or summary files.

## 6. Next sessions

Read the block (§1) → verify the script path exists → send per §4 with **no further questions**. Re-run onboarding only if the block is missing or the script is gone, and only after telling the user which of the two happened.

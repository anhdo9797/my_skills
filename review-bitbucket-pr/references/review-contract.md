# Bitbucket Pull Request Review Contract

This contract defines what counts as a finding, how severe it is, how a comment is written, and what the result looks like. It is stack-neutral — the concrete detectors for a given ecosystem come from the stack profile in `stacks/`.

Repository evidence overrides everything here. A project's own convention, visible in its instruction files or in the code next to the change, beats a general rule in this document. Say so when you rely on it.

## Contents

- [Evidence threshold](#evidence-threshold)
- [Coverage gates](#coverage-gates)
- [Quality gates](#quality-gates)
- [Severity model](#severity-model)
- [Comment format](#comment-format)
- [Deduplication and placement](#deduplication-and-placement)
- [Result format](#result-format)

## Evidence threshold

Comment only when the issue has practical value and is supported by the changed code plus the context you actually read. A valid finding connects a cause to a reachable behaviour, states the impact, and proposes the smallest correction that fits the existing architecture.

Do not comment because another implementation style exists, because a formatter owns the formatting, because a name could be marginally better, or because a refactor outside this PR would improve the system. Each of those costs the author attention and returns nothing, and enough of them make the real findings invisible.

When the requirement is unclear, ask a focused question instead of dressing an assumption up as a defect.

## Coverage gates

These three run on every review, in every stack. They exist because they catch the classes of defect that reviewers most reliably miss by reading the diff top to bottom: the string that never got translated, the function that quietly became unmaintainable, and the caller nobody updated. The stack profile tells you what each one looks like concretely.

**User-facing copy gate.** Every changed string that can reach a human — screen text, labels, titles, placeholders, tooltips, accessibility text, dialogs, notifications, errors shown to users, status names — must go through the project's localization mechanism, or have a concrete reason it does not. Anchor the comment on the exact changed literal; a vague pointer at the neighbourhood makes the author hunt for it. Internal logs, technical identifiers, API field names, and content the backend already localizes are out of scope.

**Complexity gate.** Every changed function, component, or view builder that grew past the project's own norm, or that carries two or more independent state branches (empty, loading, error, content), gets checked for whether its responsibilities are still separable and testable. Judge against the sizes actually present in this repository, not an absolute line count.

**Compatibility gate.** For every changed or removed piece of public surface — a parameter, a public method, a route, an enum or status value, an event name, a persisted field, an API contract — search for its consumers and confirm none was left behind. This is the gate that turns a green pipeline into a production incident, because a stale caller in a module the PR did not touch will still compile in many languages.

Record per changed hunk which gates applied and what each returned. A gate you did not run is not a gate that passed.

## Quality gates

### Correctness and runtime

- Branch completeness; null, empty, and invalid input; ordering; state transitions; pagination; caching; retry; synchronization.
- Async ordering, missing awaits, duplicated requests, stale state, work continuing after the owner is gone.
- Invalid casts, index access, unclosed resources, listeners and subscriptions never released, rebuild or render loops, blocking work on the UI or request thread, crash paths.
- Loading and error states terminate on every branch, and the loading, empty, failure, disabled, and success states all stay reachable.

### Security and privacy

- No hard-coded credentials, keys, tokens, secrets, or sensitive configuration.
- Check sensitive data in logs, insecure storage, missing validation or sanitization, injection, authorization scope, and exposure of user data.
- Never open a secret-bearing file to check one of these. Describe what you would need instead.

### Architecture and layering

- Each layer keeps its job: presentation renders state and owns navigation and UI effects; coordinators own state transitions and call repositories or domain operations; repositories own data access and translate transport failures into application errors; transport clients define contracts and are not reached directly from presentation code.
- Business logic, validation, transformation, dependency calls, and multi-step async work do not belong inline in UI callbacks. A genuinely trivial action, such as closing the current screen, is fine there.
- Introduce a new abstraction only for behaviour that is reusable or multi-step. A one-caller indirection adds a hop and hides nothing.
- Follow the lifecycle, ownership, and immutability conventions already used by the neighbouring code.

### Maintainability

- Comment on length only when responsibilities are materially mixed, not on a mechanical line count. Blank lines and closing brackets are not complexity.
- Split large trees with multiple independent states into purpose-named units. Prefer a real component or class when the block owns state, behaviour, or is reused.
- Watch for deep nesting, magic values, duplicated material, mixed responsibilities, and comments that only restate the code.

### Generated sources

- Generated files change through their inputs, never by direct editing. A hand-edit survives until the next build and then silently disappears.
- Check that regeneration was actually run when an input changed.

### Testing

- New behaviour gets focused coverage of the success path and the failure paths that matter. Bug fixes get regression protection.
- Check edge cases, mock fidelity, and dependence on timing, network, or execution order.
- Missing tests are a finding only when the uncovered behaviour carries concrete regression risk. "Add tests" as a reflex is noise.

## Severity model

Use the narrowest severity the impact supports. Inflated severity is the fastest way to make a review ignorable.

- `Blocker` — data loss, a serious vulnerability, failure of a primary flow, a crash on a common path, or a confirmed severe business-rule violation.
- `Major` — a clear logic defect, a likely runtime failure, an important missing edge case, large regression risk, or a substantial architecture violation.
- `Minor` — a real maintainability defect, a violated project rule, incomplete localization, or an unprotected bounded risky path.
- `Suggestion` — an optional improvement with real value, where current behaviour is already correct and safe.
- `Question` — missing business information that materially affects the verdict.

## Comment format

Write in professional Vietnamese (or the language the user requested), using this shape:

```text
**[Major] Có nguy cơ sử dụng BuildContext sau async gap**

Sau `await submit()`, widget có thể đã bị dispose nhưng nhánh này vẫn dùng `context` để điều hướng. Trường hợp xảy ra khi người dùng rời màn hình trước lúc request hoàn tất, có thể gây runtime warning hoặc điều hướng sai.

Đề xuất kiểm tra `context.mounted` trước khi điều hướng, theo lifecycle pattern đang dùng trong feature này. Nên bổ sung test cho trường hợp dispose trước khi request hoàn tất.
```

Every comment carries four things, in this order:

1. Severity marker and a specific title — specific enough that the title alone identifies the problem.
2. The concrete trigger or the evidence.
3. The impact on a user or the system.
4. The minimal correction, plus a focused test when one would protect the defect.

For ambiguity:

```text
**[Question] Cần xác nhận hành vi khi cập nhật thất bại**

Implementation hiện đóng màn hình khi request lỗi, nhưng PRD/acceptance criteria chưa mô tả nhánh này. Thông tin này quyết định việc đóng màn hình là chủ ý hay làm mất cơ hội retry.

Nhờ team xác nhận khi API lỗi thì màn hình cần giữ lại để retry hay vẫn đóng như hiện tại.
```

Keep the severity marker in the visible title. The author needs to triage without opening every thread.

## Deduplication and placement

- Compare file, affected behaviour, root cause, trigger, and impact against every existing comment before posting.
- Do not repeat an unresolved comment, even when your severity or wording differs.
- When one pattern repeats, comment once on a representative changed line and list the other locations. Group only within a scope the reader can verify — if the listed locations sit in different hunks, name their `path:line` explicitly.
- Post inline only on a line that is changed at the current head commit.
- Fall back to a general comment carrying an explicit `path:line` only when the connector cannot express the correct anchor.

## Result format

Return these sections, in this order, in Vietnamese. Keep the recommendation and coverage values in English so they stay machine-comparable across reviews.

```markdown
## Tổng quan

- PR: `<title>` (`<source>` → `<destination>`)
- Chế độ: `Live review | Dry run`
- Mục tiêu: <confirmed purpose, or a note that context was missing>
- Phạm vi: <files reviewed, relevant consumers, and coverage if the PR was too large for all of it>
- Pipeline: <status, or unavailable>

## Thống kê

- Blocker: <count>
- Major: <count>
- Minor: <count>
- Suggestion: <count>
- Question: <count>

## Comment đã đăng

| Mức độ | Vị trí | Nội dung | Comment |
| --- | --- | --- | --- |
| Major | `path/file.ext:42` | <short issue> | <comment URL/ID> |

Use `Không có.` when nothing was posted. Add a `Comment đăng thất bại` subsection when a write failed.
In dry run, title this section `Comment sẽ đăng (dry run — chưa gửi lên Bitbucket)` and leave the last column empty.

## Các vấn đề chính

<Short prioritized list, or `Không phát hiện vấn đề cần chỉnh sửa.`>

## Kiểm tra

- `<command or pipeline check>`: <result>

Use `Không chạy kiểm tra bổ sung.` when none was warranted.

## Kết luận

- Khuyến nghị: `Approve | Approve with suggestions | Request changes | Need clarification`
- Localization: `reviewed | not applicable`
```

Counts are unique root causes, not comment attempts. Report posted comments and failed attempts truthfully — the summary is the only part most readers will read, so an inaccuracy there is the most expensive kind.

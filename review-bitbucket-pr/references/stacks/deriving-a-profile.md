# Deriving a stack profile for an unfamiliar repository

Use this when the diff's main risk sits outside a written profile. The goal is not to become an expert in the ecosystem — it is to find, in a few targeted reads, what this specific repository already treats as correct, so that findings cite the project's own standard instead of a generic one.

A finding that says "this repo localizes through `t('key')` everywhere else, and this line hard-codes the string" is actionable. A finding that says "consider using i18n" is not, and will be wrong roughly as often as it is right.

## Step 1 — identify the ecosystem

Read the manifest at the repository root: `package.json`, `go.mod`, `pyproject.toml` / `requirements.txt`, `build.gradle` / `pom.xml`, `Package.swift`, `*.csproj`, `Gemfile`, `composer.json`, `Cargo.toml`. It gives you the language, the framework, the test runner, and the lint setup in one read.

## Step 2 — fill in the three coverage gates

You need one concrete answer per gate. Get each from the code, not from memory.

**User-facing copy.** Find the localization library in the manifest, then grep one existing UI file for how a translated string is actually fetched. That call shape is your detector — any changed literal in a rendering position that does not use it is a candidate. If the repository has no localization mechanism at all, the gate does not apply; record that rather than inventing a requirement.

**Complexity.** Do not import an absolute line limit. Look at three or four existing functions in the same directory and use their size and structure as the norm. Check the lint config for an enforced limit (`max-lines-per-function`, `funlen`, `cognitive-complexity`) — if one exists, it is the project's answer and you should not restate what the linter already fails on.

**Compatibility.** Determine what "public surface" means here: exported symbols in an index file, an OpenAPI or protobuf schema, a migrations directory, a routes table, an events catalogue. Then, for each changed item of that kind, grep the repository for its consumers. In dynamically typed languages this gate matters most, because nothing will fail at build time.

## Step 3 — find the conventions that produce most findings

Three quick checks, each worth more than a broad read:

- **Error and async handling.** Open the nearest existing sibling of a changed file and see how it handles failure — thrown domain error, result type, error boundary, retry wrapper. A change that handles failure differently from its neighbours is a real finding; a change that handles it differently from your preference is not.
- **Layering.** Infer boundaries from the directory names actually present (`handlers/`, `services/`, `repositories/`, `components/`, `hooks/`). A changed file reaching two layers down past its own is worth checking.
- **Generated files.** Look for `// Code generated`, `@generated`, `DO NOT EDIT` headers, or generation entries in the build config and `.gitignore`. Hand-edits there disappear at the next build.

## Step 4 — record what you could not determine

If a convention stayed unclear after these reads, say so in the result rather than substituting a general rule and presenting it as the project's standard. "This repo has no visible localization setup, so the copy gate was not applied" is honest and lets the author correct you in one line.

## Step 5 — promote it if it recurs

If you review this stack more than once or twice, write a real profile: copy the structure of `flutter-dart.md`, fill in the detectors you derived, save it in this directory, and add it to the selection list in `SKILL.md` step 4. The second review then starts from evidence instead of rediscovering it.

## Common cross-language traps

Worth checking in almost any ecosystem, because they survive review and type-checking alike:

- A new enum, union, or status value added while `switch`/`match` sites elsewhere fall through a default branch.
- A field renamed in a serialized payload while stored or in-flight data still carries the old name.
- A nullable value newly made non-nullable, or the reverse, without checking existing callers and persisted rows.
- An `await` / `async` removed or added so that ordering changes, or a promise/future created and never awaited.
- A resource opened without a guaranteed close on the error path.
- A configuration default changed, which silently alters behaviour for every environment that did not override it.

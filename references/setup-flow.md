# Setup flow (new project or new plan)

Goal: a working `.superpowers/sdd/<PLAN_ID>/` folder, a baseline gate, decisions O-1…, and a next-session prompt.
Do not write feature code during setup.

## 1. Detect, then look

Run `python3 $ES/scripts/detect_stack.py <repo root>`. It prints suggested
`PROFILES` (backend / mobile / web; generic when nothing matches), per-stack gate commands, locale files, rules
files, plan candidates, test folders, the current branch, and whether the repo is a monorepo. Then read the rules
file, the plan file and the build files yourself to confirm. Pre-fill every answer you can and ask only for what is
left. The owner confirms or overrides; never ask them to type what detection already found.

If `.superpowers/sdd/` already holds a plan, ask whether this is a **second plan** (new folder) or a **resume**
(switch to the session loop).

## 2. Interview (AskUserQuestion, ≤4 questions per round, recommendation first)

Round 1: identity and scope
- Project name + plan id (UPPER_SNAKE, used as the folder name), e.g. `ACME_API_REVAMP`. Default: the plan file's
  stem without dates or a `-plan` suffix, upper-snaked (`2026-11-01-recipes-v2-plan.md` → `RECIPES_V2`).
- Stack profile(s): show what detection found ("Detected: backend (.NET at backend/) + web (Angular at
  frontend/admin)") with options **Use detected (Recommended)** / **Change**. Profiles: `backend`, `mobile`, `web`,
  `generic`; several are allowed in a monorepo, and each adds its checklist and rules.
- **Coding rules**: show a short summary of the default rules for the chosen profiles
  (`profiles/<p>/coding-rules.md`, ten lines at most) and ask: **Use the defaults (Recommended)** / **Edit them**
  (walk the sections with the owner and change what they say, then write the result) / **Replace with our own**
  (the owner gives a file path or pastes the rules) / **Repo rules file only** (no coding-rules.md). If the repo
  already has a rules file, say so, and recommend defaults + repo file together (the repo file wins on conflicts).
- Plan file path (phases/tasks). If none exists, offer superpowers:writing-plans first.
- Rules file(s) that are the source of truth (AGENTS.md, CLAUDE.md, CONTRIBUTING.md).

Round 2: gates
- Build, lint/analyze, format (explicit files only), unit tests, e2e/live check (curl suites, device run,
  Playwright …).
- Function-length limit (default 60 for backend, 40 for mobile and web) and any other structural rule the gate
  should scan.
- Extra gate snippets (`EXTRA_GATES`, from `profiles/<p>/gate-snippets/`): offer the ones that fit the detected
  stack (e.g. layering + doc comments for a layered backend with required doc comments; a stack lock when several
  worktrees share one container stack; core-imports-features + preview isolation for a mobile app with design
  previews).
- Localization: languages and locale files. If there is more than one language, "every user-visible key in every
  locale file in the same batch" becomes a rule.

Round 3: people and models
- Implementer lanes, in order, with fallbacks (see `lanes.md`). Example: H = Haiku high via /claude-delegate, then
  /opencode-delegate Anthropic provider, then a plain Agent-tool Haiku; G = agy (evidence untrusted).
- Reviewer: model (default opus), effort (default medium), agent name (default `<plan-id-lower>-reviewer`).
- Fact-map / survey helper model (default sonnet, read-only).
- Batch size in minutes (default 30) and whether pairs are the default (yes).

Round 4: git and safety
- Base branch, work branch(es), worktree tracks if any.
- Paths to stage (explicit list), paths never to stage (real config, secrets, backups).
- Owner-reserved decision categories (defaults in `owner-decisions.md`). Add anything the owner wants to see
  first, such as copy changes, pricing or migrations.
- Forbidden git verbs (default: stash, checkout, restore, reset, worktree changes, push without asking).

## 3. Generate

1. Write `answers.json` (schema in `answers-schema.md`) into the scratchpad.
2. `python3 $ES/scripts/scaffold.py --answers <answers.json> --repo <repo root>`
   - It refuses to overwrite an existing folder unless you pass `--force`. Never use `--force` on a live plan
     without the owner's OK. The script backs up overwritten files as `*.bak-<date>`.
   - `UNFILLED:` lists setup keys missing from answers.json. Add them and re-run with `--force`.
   - `FILL BY HAND:` lists the `<sha>`, `<total>`, `<scope>` fields and `{{NAME — hint}}` placeholders in the
     handoff, progress and next-session prompt. Fill them after the baseline (step 4), from git and the plan.
   - Placeholders such as `{{BASE}}`, `{{BATCH_ID}}` and `{{RUN}}` in brief/review templates are per-batch; leave
     them alone.
   - Shell-sensitive values (`TEST_FAILURES_EXTRACT`, `FORMAT_CHECK`) are written into single-quoted bash strings,
     and the script escapes quotes. Write them in answers.json exactly as you would type them in a shell (JSON only
     needs `\\` for a backslash). Do not repeat `.superpowers/` in `NEVER_STAGE`; the template adds it.
3. Coding rules: for mode `edit`, open the generated `coding-rules.md` and apply the owner's changes section by
   section. Offer (do not do it unasked) to merge the rules into the repo's own rules file, so that non-orchestrated
   sessions follow them too.
   `check.sh`: replace each `HOOK:` block with the project's real commands (see `profiles/<stack>/gate-hooks.md`).
   Keep the contract: it prints one line per gate and ends with `ALL GATES PASS` or `GATES FAILED`.
4. Reviewer agent: list `~/.claude/agents/` first. The name must be unique per plan (`<plan-id-lower>-reviewer`).
   Reuse an existing agent only when it belongs to this same plan; never overwrite another plan's reviewer. Show
   the owner `reviewer-agent.md`. On a yes, copy it to `~/.claude/agents/<name>.md`. To let
   the reviewer edit without prompts, add project allow rules (Edit/Write on source dirs and the plan folder) to
   `.claude/settings.local.json`, but only with the owner's yes, because it is persistent configuration.
5. Make sure `.superpowers/` is gitignored. If it is not, propose the one-line `.gitignore` change and wait for the
   owner's yes.

## 4. Baseline

Run `check.sh HEAD > runs/baseline/gate.log 2>&1` (in the background if it is slow). Use `--no-tests` only when
the repo has no tests yet, and write that into the baseline line. A `TOOL NOT FOUND` line is an environment
problem (toolchain missing from PATH), not a code finding: fix PATH in check.sh or tell the owner, then re-run.
The survey starts at the first plan phase that is not closed, unless the owner names another one. Record in the handoff "Gates
baseline": build state, test counts, known failures (copy them into `known-test-failures.txt`), and legacy debt
counts (functions over the limit, multi-type files). Legacy debt gets fixed whenever a batch touches the file.

## 5. Decisions and first prompt

- Record the setup answers as rows O-1… in the decisions table: lanes, reviewer, batch size, staging rules,
  languages, reserved categories. Each row gets its reason in brackets.
- Write `NEXT_SESSION_PROMPT.md` from the template. Show it to the owner in chat.
- First real work: the **survey** of phase 1 (`survey-brief-template.md`, read-only lane). It produces
  `runs/<phase>-survey.md`. Append ORCHESTRATOR RULINGS + BATCH ORDER (each batch marked MECHANICAL or JUDGEMENT,
  paired where file sets are disjoint).

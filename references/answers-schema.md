# answers.json schema (input to scripts/scaffold.py)

Every key becomes a `{{KEY}}` placeholder in the templates. Strings unless noted. Keys marked (d) are derived by
the script, so do not set them.

```json
{
  "PROJECT_NAME": "Acme API",
  "PLAN_ID": "ACME_API_REVAMP",
  "PLAN_TITLE": "Acme API revamp",
  "PROFILES": ["backend"],
  "PLAN_FILE": "docs/plans/2026-11-01-api-revamp.md",
  "RULES_FILES": "AGENTS.md, CLAUDE.md",
  "CONTRACT_DOCS": "docs/api-contract.md (or none)",
  "BASE_BRANCH": "main",
  "WORK_BRANCH": "dev_revamp",
  "SOURCE_DIRS": "src tests",
  "TEST_DIRS": "tests",
  "BUILD_CMD": "npm run build",
  "LINT_CMD": "npm run lint",
  "FORMAT_CHECK": "npx prettier --check",
  "SRC_PATTERN": "^src/.*\\.(ts|tsx)$",
  "TEST_FAILURES_EXTRACT": "grep -E '^ FAIL ' | awk '{print $2}'",
  "TEST_CMD": "npm test",
  "E2E_CMD": "./tests/run_e2e.sh <suites> (or none)",
  "LIVE_CHECK": "docker compose up + curl every new/changed endpoint",
  "FN_MAX_LINES": 60,
  "LANGUAGES": "EN + AR",
  "LOCALE_FILES": "src/i18n/en.json, src/i18n/ar.json",
  "LANES": [
    {"id": "H", "name": "Haiku high via /claude-delegate", "when": "every batch and fix round",
     "command": "node <claude-delegate skill dir>/scripts/relay.mjs --brief <b> --cd <tree> --model claude-haiku-5-5 --effort high --timeout 2h --out-dir <runs/id>",
     "resume": "--session <sessionId from result.json>",
     "fallback": "OpenCode Anthropic provider, then a plain Agent-tool Haiku"},
    {"id": "G", "name": "agy (Gemini)", "when": "only when H is out of quota",
     "command": "node <agy-delegate skill dir>/scripts/relay.mjs --brief <b> --cd <tree> --out-dir <runs/id>",
     "resume": "--conversation <id from result.json>",
     "fallback": "H", "untrusted_evidence": true}
  ],
  "REVIEWER_MODEL": "opus",
  "REVIEWER_EFFORT": "medium",
  "REVIEWER_AGENT": "acme-api-revamp-reviewer",
  "HELPER_MODEL": "sonnet",
  "BATCH_MINUTES": 30,
  "STAGE_PATHS": "src tests docs",
  "NEVER_STAGE": "config/.env.* (except *.example), secrets/*, *.bak-*",
  "OWNER_RESERVED": ["user-visible behaviour or copy", "contract/API deviations",
                     "data-loss or security trade-offs", "real scope, cost or schedule changes"],
  "FORBIDDEN_GIT": "stash, checkout, restore, reset, switch, worktree add/remove, push (unless asked)",
  "OWNER_NAME": "the owner",
  "CODING_RULES": {"mode": "default", "file": "docs/our-rules.md (only for mode=replace)"},
  "PARALLEL_PAIRS": "auto (run PARALLEL-OK pairs in git worktrees) | off",
  "WORKTREE_DIR": "(optional) where worktrees go; default <repo parent>/<repo name>.worktrees",
  "WORKTREE_SETUP_CMD": "npm ci | flutter pub get | none (run once in each new worktree)",
  "WORKTREE_COPY_FILES": [".env (optional list of local untracked files to copy into worktrees; owner-reserved)"],
  "GATE_TIMEOUT_SECONDS": 1800,
  "REVIEWER_AGENT_SCOPE": "project (.claude/agents/, default) | user (~/.claude/agents/)",
  "EXTRA_GATES": ["layering", "doc-comments", "pre-stack-lock", "suite-parse"],
  "COMMENT_POLICY": "(optional; profile default) how much to comment"
}
```

Derived (d): `PLAN_DIR` (`.superpowers/sdd/<PLAN_ID>`), `PLAN_ABS` (its absolute path), `REVIEWER_AGENT_PATH`,
`WORKTREE_DIR_RESOLVED`, `TODAY`, `LANES_TABLE` (markdown table),
`LANES_LIST` (one line per lane), `OWNER_RESERVED_LIST` (bullets), `PROFILE_NAMES`, `REPO_ROOT` (from `--repo`).

`CODING_RULES.mode`: `default` = the profile rules as they are; `edit` = the profile rules, then edited with the
owner in chat; `replace` = copy the owner's own file (`CODING_RULES.file`) as coding-rules.md; `repo` = no
coding-rules.md, so the repo's rules file is the only source. Every mode except `repo` appends
`<PLAN_DIR>/coding-rules.md` to `RULES_FILES`.

`EXTRA_GATES`: names of `profiles/<p>/gate-snippets/<name>.sh` to copy into `gates.d/`. Backend: `layering`,
`doc-comments`, `pre-stack-lock`, `suite-parse`. Mobile: `core-imports-features`, `generated-up-to-date`,
`preview-isolation`. Snippets named `pre-*` run before the build; the rest run before e2e.

Validation: `PLAN_ID` must be UPPER_SNAKE (`[A-Z][A-Z0-9_]{1,63}`), because it names a folder and branches. Keys that are not in
this schema are reported as `UNKNOWN KEY (ignored)` with a "did you mean" hint. Keys starting with `_` (such as the `_confirm`
list of a draft) are ignored on purpose. `scripts/detect_stack.py <repo> --draft-answers` prints a complete draft.
`scaffold.py` also writes `<plan>/config.json` (the worktree, timeout and reviewer-agent settings) for `worktree.py` and `doctor.py`.

Rules of thumb
- Use `"none"` rather than leaving a key out. A missing key stays as `{{KEY}}` and is reported as UNFILLED.
- `PROFILES` order decides the order of the checklist sections. `generic` is always added as the base.
- Profile defaults (`profiles/<p>/defaults.json`) fill `STACK_SUMMARY`, `SRC_PATTERN`, `MIGRATIONS_GLOB`,
  `FN_MAX_LINES`, `LIVE_CHECK`, `TEST_FAILURES_EXTRACT` and the forbidden-pattern rules. With several profiles, the
  last one wins for single values, so set `FN_MAX_LINES` and `SRC_PATTERN` explicitly in a monorepo.
- Gate-only keys: `SRC_PATTERN` (regex of non-test source files), `MIGRATIONS_GLOB`, `FORMAT_CHECK` (a check-only
  formatter that takes file paths), `TEST_FAILURES_EXTRACT` (a filter that reads test output on stdin and prints
  one failing test id per line).
- `untrusted_evidence: true` on a lane adds the "pre-check its report + reviewer re-runs every gate" rule to the
  rule checklist.

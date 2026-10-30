| # | Date | Decision |
| --- | --- | --- |
| O-1 | {{TODAY}} | **Workflow = es-orchestrator**: orchestrator only; implementer lanes per ROLES; paired batches of ≈ {{BATCH_MINUTES}} min; fresh {{REVIEWER_MODEL}} reviewer per pair; full report file to {{OWNER_NAME}} before every commit. [owner, setup] |
| O-2 | {{TODAY}} | **Gates**: `check.sh` wraps build, lint, format (explicit files), tests vs known failures, function length ≤ {{FN_MAX_LINES}}, structure scans, locale parity, e2e/live checks. [owner, setup] |
| O-3 | {{TODAY}} | **Languages**: {{LANGUAGES}}. Every user-visible text goes in all locale files in the same batch. [owner, setup] |
| O-4 | {{TODAY}} | **Owner-reserved decisions**: see RULE CHECKLIST item 3; everything else is ruled by the orchestrator with a reason. [owner, setup] |
| O-5 | {{TODAY}} | **Git**: never {{FORBIDDEN_GIT}}; stage explicit paths only; never stage {{NEVER_STAGE}}. [owner, setup] |
| O-6 | {{TODAY}} | **Coding rules**: {{CODING_RULES_SUMMARY}}. Rules files in force: {{RULES_FILES}}. [owner, setup] |
| O-7 | {{TODAY}} | **Stack profiles**: {{PROFILE_NAMES}} (detected from the repo, confirmed by {{OWNER_NAME}}). [owner, setup] |
| O-8 | {{TODAY}} | **Parallel pairs**: {{PARALLEL_PAIRS}} (auto = run a pair in git worktrees at the same time when the survey tags it PARALLEL-OK; off = always sequential). Worktrees in {{WORKTREE_DIR_RESOLVED}}; setup `{{WORKTREE_SETUP_CMD}}`. Gate timeout {{GATE_TIMEOUT_SECONDS}} s per command. [owner, setup] |

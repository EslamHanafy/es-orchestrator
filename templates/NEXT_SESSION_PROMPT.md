Use es-orchestrator to continue {{PLAN_TITLE}} as ORCHESTRATOR. Read {{PLAN_DIR}}/ORCHESTRATOR_HANDOFF.md first: the newest
"END STATE" block at the top of LIVE STATUS, then "⛔ RULE CHECKLIST" (walk it before EVERY brief, dispatch, ruling and commit,
and check every new ruling against the OWNER DECISIONS table), "ROLES", "OWNER DECISIONS & RULINGS" (newest rows), then
review-checklist.md and performance-checklist.md. Then progress.md (this and the last session's lines),
review-lessons-self-check.md, and only the survey/fact files the NEXT item names.

STATE: {{STATE — HEAD sha per branch, what is committed, what is uncommitted, what is running (pid / out-dir / session id)}}.

FIRST: give {{OWNER_NAME}} a status with done/left percentages (by count and by effort), then ask about the open OWNER-REVIEW
items in the END STATE block, then continue NEXT in the order listed there.

LANES: as in ROLES/Workflow in the handoff ({{LANES_SHORT}}). Always run_in_background; never poll.
Reviewers: a fresh {{REVIEWER_MODEL}} `{{REVIEWER_AGENT}}` per pair.

STANDING RULES: status first, then keep dispatching until {{OWNER_NAME}} says stop. Before EVERY commit, SEND the full review
report FILE plus a plain summary. Every issue in a touched file is fixed before the commit. No source file may be newer than the
gate log (re-gate if one is). Never {{FORBIDDEN_GIT}}. Stage explicit paths with the NUL-safe pipeline; never stage {{NEVER_STAGE}}.
{{PROJECT_STANDING_RULES — the 3–6 rules that bit this project most}}

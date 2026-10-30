# ▶▶ {{PLAN_TITLE}} — ORCHESTRATOR HANDOFF (read this first after every compact; created {{TODAY}})

## ⛔ HARD RULE — COMMIT GATE
NEVER commit anything (implementer batch, fix round, or my own small follow-up) before {{OWNER_NAME}} has the FULL
per-checkpoint review report FILE (every line of review-checklist.md, every group of performance-checklist.md, every
section of {{RULES_FILES}}) with evidence, plus a plain-language summary, AND every point has passed. Every issue found is
fixed before the commit, even when it lives in OLD code of a file the batch touches. `check.sh` is a gate, never the review.
Update THIS handoff + progress.md after EVERY review and EVERY commit.
REPORT WORDING: never bare checklist ids. Name each line in plain words ("Run really finished", "Every changed line read",
"Performance — <group>", "{{RULES_FILES}} — <section>", "Function length (max {{FN_MAX_LINES}} lines, SOLID)", "Bookkeeping").

## ⛔ ROLES
- **Me = ORCHESTRATOR ONLY.** I write surveys, rulings, batch order and briefs; make every non-reserved decision; dispatch
  implementers and reviewers; read the reviewer's report and own the verdict; send the report to {{OWNER_NAME}}; run the gate;
  commit; and keep the books. I write no feature code, except tiny reviewer-handed follow-ups that need no design decision.
- **IMPLEMENTER LANES** (details + commands in "Workflow"):
{{LANES_LIST}}
  Fact maps / surveys = {{HELPER_MODEL}} read-only agents (one output file). No sub-workers.
- **PAIRS:** adjacent batches with disjoint files run as a pair: A, then B on top of the uncommitted A (each in a new session),
  ONE review for both (BASE = the commit before A). A batch stays single only when {{OWNER_NAME}} must answer between them.
  **PARALLEL pairs** ({{PARALLEL_PAIRS}}): when the survey tags a pair PARALLEL-OK, A and B run AT THE SAME TIME, each in its own git
  worktree (`worktree.py` of the es-orchestrator skill; worktrees in {{WORKTREE_DIR_RESOLVED}}), are landed together on the main tree, and
  from then on are gated, reviewed and committed exactly like a sequential pair (references/parallel-pairs.md).
- **REVIEW:** a FRESH {{REVIEWER_MODEL}} subagent per pair (`{{REVIEWER_AGENT}}`, effort {{REVIEWER_EFFORT}}, acceptEdits).
  JUDGEMENT batches, fix rounds and phase close-outs → FULL line-by-line (review-full-template.md); MECHANICAL batches only →
  LIGHT (review-light-template.md). Evidence first, no blind re-runs. Fix round → same lane, then a NEW reviewer.
- Tell {{OWNER_NAME}} before big strong-model jobs (phase close-outs, multi-batch sweeps).

## ▶ LIVE STATUS — RESUME HERE FIRST
(Older session blocks move to archive-ORCHESTRATOR_HANDOFF-through-s<N>.md; leave a one-line pointer here.)
**▶▶ SESSION 1 END STATE ({{TODAY}}; setup) — RESUME HERE FIRST:**
- PROGRESS: 0 / <total> plan tasks ✅ (0 % by count, 0 % by effort). PHASES CLOSED: none. OPEN: <phase 1>.
- STAGE: <stage> (NONE · PLANNED · IMPLEMENTED-UNREVIEWED · REVIEWED-UNCOMMITTED · FIX-ROUND-NEEDED · COMMITTED) · NEXT MODE: <next mode> · LIVE WORKTREES: none.
- BRANCHES: {{WORK_BRANCH}} <sha> (from {{BASE_BRANCH}}). Merge-gate counter 0.
- AT STOP: nothing running. Baseline gate: runs/baseline/gate.log.
- OWNER-REVIEW ITEMS: none.
- NEXT (in order): 1. Survey phase 1 (survey-brief-template.md → runs/<phase>-survey.md). 2. Rulings + batch order. 3. First pair.
- LANES: as in ROLES. LESSONS: none yet.

## OWNER DECISIONS & RULINGS (binding; reason in brackets)
{{DECISIONS_TABLE}}

## ⛔ RULE CHECKLIST (walk it before EVERY brief, dispatch, ruling and commit)
1. Batch ≈ {{BATCH_MINUTES}} min (files × complexity); more than ~15 % over → split BEFORE dispatch; unsplittable → ask {{OWNER_NAME}} first.
2. Batches are PAIRED (A, then B on the uncommitted A, ONE review). Single only when {{OWNER_NAME}} must answer between them.
3. Implementer DECISIONS → I rule them myself with a reason (survey/rulings file) and report them in the next summary. Only
   owner-reserved ones go to {{OWNER_NAME}} first, with my recommendation:
{{OWNER_RESERVED_LIST}}
4. Every ruling is checked against the OWNER DECISIONS table before it is recorded.
5. Before EVERY dispatch, an existing brief is re-checked against the current code, BASE, rulings and file:line facts, and updated first.
6. REPORT.md complete (per-ruling list, DECISIONS, every self-check line) before the review; otherwise a report-only resume turn.
7. Untrusted-evidence lane batch → I pre-check the report's claims, and the reviewer re-runs every gate and live check.
8. Commit gate: {{OWNER_NAME}} has the FULL report FILE + summary; every finding fixed; gate ALL GATES PASS on this tree; no source
   file newer than the gate log; explicit-path staging; plan Status line + phase row updated in the same commit.
9. After every review and commit: progress ledger line + LIVE STATUS + review-cost line.
10. Every deferral → a dated `ADDED YYYY-MM-DD:` line in the plan. No bare ids in reports. Never touch real config/secrets
    without an O-row. Never {{FORBIDDEN_GIT}}.
11. Every user-visible text in ALL locale files ({{LANGUAGES}}: {{LOCALE_FILES}}) in the same batch; briefs say it, reviewers check it.
12. Pair-A briefs never start a long full gate (B edits during it). In a PARALLEL pair each implementer gates its own tree; the combined
    tree is gated by me after landing (`runs/<B>/integration-gate.log`) BEFORE the review.
13. Parallel pair only when: the previous pair is committed (clean tree), the file sets are disjoint, the batches do not depend on each
    other, and no shared port / database / container is used (or the stack lock is on). Worktrees are removed after the commit.
14. A single-step mode (plan / orchestrate / review / commit) does ONLY its stage, records it with `status.py --set-stage` and names the
    next mode. `commit` needs the review report's OWNER_REPORT_SENT marker.

## Workflow (binding)
**Dispatch** (`W={{PLAN_DIR}}`; always `run_in_background`; never poll, wait for the notification):
{{LANES_TABLE}}
- `mkdir -p $W/runs/<id>; touch $W/runs/<id>/START` right before each dispatch (file ownership for pair reviews).
- Resume, never restart: same command + the lane's resume flag + a short delta brief. Quota error → fallback lane at once.
- Save the report verbatim to `$W/runs/<id>/REPORT.md` (the relay's final message).

**Parallel pair:** `worktree.py add --id A --id B` (clean tree) → dispatch each lane with `--cd <worktree>` → `worktree.py snapshot --id <x>` for each →
`worktree.py land --id A --id B` → combined gate → review → commit → `worktree.py remove --all`. Land refuses overlapping files, stale gate
evidence and a moved HEAD; on any refusal fall back to a sequential pair.

**Review:** copy review-full-template.md (or review-light-template.md) to `review-<A>+<B>-prompt.md`, fill it, and dispatch the
Agent tool (`subagent_type: {{REVIEWER_AGENT}}`, `model: {{REVIEWER_MODEL}}`). It writes `<A>+<B>-review-report.md` (+ `<id>-fix1-brief.md`).

**Commit:** gate freshness (see RULE 8) → stage explicit paths (`{{STAGE_PATHS}}`) with the NUL-safe pipeline:
`git status --porcelain -uall -- {{STAGE_PATHS}} | awk '{print $2}' | tr '\n' '\0' | xargs -0 git add -A --`
Never stage: {{NEVER_STAGE}}, `.superpowers/`. Message: `<type>(<scope>): <batch ids> — <one-line summary>` + the attribution line. Before the commit the marker `<A>+<B>-OWNER_REPORT_SENT`
exists in this folder (created right after the report was sent to {{OWNER_NAME}}).

**Gates:** build `{{BUILD_CMD}}` · lint `{{LINT_CMD}}` · format `{{FORMAT_CHECK}}` · tests `{{TEST_CMD}}` · e2e `{{E2E_CMD}}` · live
check: {{LIVE_CHECK}}. All are wrapped by `$W/check.sh <BASE> [options]`, which ends with ALL GATES PASS / GATES FAILED.

**Bookkeeping:** ledger line per review and commit; LIVE STATUS replaced (not appended); plan Status line + phase commit list in
the same commit; phase close-out ticks the roadmap row; every new defect class → a line in review-lessons-self-check.md.

**Rhythm** (`full` mode; a single-step mode stops after its own stage): don't stop between batches; one chat line per milestone; next-session prompt in chat at each phase end.

**Gates baseline ({{TODAY}}, HEAD <sha>):** build <state>; tests <n>/<n>; known failures: known-test-failures.txt; legacy debt
<n functions over {{FN_MAX_LINES}} lines, n multi-type files> (fixed when a batch touches the file).

## Checklists
- MANDATORY REVIEW CHECKLIST → `review-checklist.md` (profiles: {{PROFILE_NAMES}})
- PERFORMANCE CHECKLIST → `performance-checklist.md`
- Implementer self-check → `review-lessons-self-check.md` (embedded in every brief; grows with every review)

## Key paths
- Plan: `{{PLAN_FILE}}` · rules: {{RULES_FILES}} · contract/spec: {{CONTRACT_DOCS}}
- This folder: gate `check.sh` (+ fnlen-allow.txt, forbidden-allow.txt, known-test-failures.txt); templates brief-template.md,
  survey-brief-template.md, review-full-template.md, review-light-template.md; working files progress.md, runs/.
- Reviewer agent: `{{REVIEWER_AGENT_PATH}}` (source: reviewer-agent.md here).
- Resume prompt: NEXT_SESSION_PROMPT.md (rewritten at every session end; backups *.bak-<date>s<N>).

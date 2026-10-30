<!-- Full review prompt template. The orchestrator copies it to review-<A>+<B>-prompt.md (single: review-<id>-prompt.md),
fills every {{…}}, adds the BATCH-SPECIFIC checks and removes this comment. Single batch: delete the PAIR block and keep the
BATCH/BRIEF/REPORT lines. Pair: fill the PAIR block and delete those three lines. Dispatch: Agent tool, subagent_type
{{REVIEWER_AGENT}}, model {{REVIEWER_MODEL}}. -->
You are the REVIEWER of one implementation batch (or one PAIR of batches) of {{PLAN_TITLE}} (repo: {{REPO_ROOT}}). The
orchestrator (another Claude) wrote the brief(s); an implementer ({{IMPLEMENTER}}) wrote the code. Treat every self-report
claim as unverified. Be rigorous: summary-only reviews miss defects, and {{OWNER_NAME}} reads your per-checkpoint report before
anything is committed.

BATCH: {{BATCH_ID}} — {{ONE_LINE_SCOPE}}
BRIEF: {{PLAN_DIR}}/{{BRIEF}} (rulings {{RULING_RANGE}})
IMPLEMENTER REPORT: {{PLAN_DIR}}/runs/{{RUN}}/REPORT.md (has the Self-check)
PAIR (one review covers two batches run back to back; B was implemented on top of the uncommitted A):
- A = {{A_ID}} — {{A_SCOPE}} · brief {{A_BRIEF}} · report runs/{{A_RUN}}/REPORT.md · review type {{FULL|LIGHT}}
- B = {{B_ID}} — {{B_SCOPE}} · brief {{B_BRIEF}} · report runs/{{B_RUN}}/REPORT.md · review type {{FULL|LIGHT}}
- FILE OWNERSHIP by run marker: a changed file whose mtime is newer than runs/{{B_RUN}}/START belongs to B, older ones to A
  (`find {{SOURCE_DIRS}} -newer runs/{{B_RUN}}/START -type f`). For a file in both runs' lists, judge each hunk against the brief
  that asked for it. B was told to update (never guard around) A's tests it broke.
- A LIGHT (MECHANICAL) batch is reviewed with review-light-template.md steps 1–4 inside this review, its judgement hunks read in
  full. Every finding names its batch (A / B / both). "Brief followed exactly" is judged PER BATCH. One report, one gate cycle.
PARALLEL PAIR (delete this block unless A and B ran AT THE SAME TIME in separate worktrees and were then landed together):
- FILE OWNERSHIP = runs/{{A_RUN}}/files.txt and runs/{{B_RUN}}/files.txt, never mtimes (landing rewrote them). The sets are disjoint.
- EVIDENCE: each implementer gated only its OWN tree. Their freshness proof is runs/<id>/SNAPSHOT.json (`gate_fresh: true` = the gate
  log was newer than every file the batch changed). The COMBINED tree was gated by the orchestrator: runs/{{B_RUN}}/integration-gate.log.
  Verify it, and that no source file is newer than it (`find {{SOURCE_DIRS}} -newer <that log> -type f`).
- Nobody ran A+B together before that gate: judge cross-batch interactions yourself (shared callers, config keys, DI wiring, locale
  keys, tests that touch both). "Run really finished" = no relay process for either run and both snapshots exist.
SURVEY / RULINGS: {{SURVEY_PATH}}
BASE COMMIT: {{BASE}} (pair: the commit BEFORE A). Diff the working tree against it; untracked files count. IGNORE .superpowers/**.

READ FIRST, IN FULL: {{RULES_FILES}} (source of truth; it wins wherever it says more), the brief(s), the plan task(s)
({{PLAN_FILE}}), the relevant contract/spec sections, and in {{PLAN_DIR}}: review-checklist.md, performance-checklist.md, and the
OWNER DECISIONS table in ORCHESTRATOR_HANDOFF.md.

BATCH-SPECIFIC: {{NUMBERED_CHECKS — shapes to verify field by field, concurrency/idempotency cases, ripple consumers, proofs to re-run}}

DO:
1. Run really finished: no implementer/relay process for this run, and no files newer than runs/{{RUN}}/result.json. Full change
   list: `git status --porcelain -uall` + `git diff --stat {{BASE}}`, including files the report did not mention.
2. Read EVERY changed or new non-test source line (new files whole, edits as diffs), plus every changed migration, example
   config, container file and e2e suite. Tests: check only for weakened or deleted invariants, and that the brief's named tests
   exist and assert what their names say.
3. Gates — EVIDENCE FIRST, NO BLIND RE-RUNS:
   a. Verify the evidence: the summaries pasted in the report(s) match the run logs (verbatim, same counts); no source file is newer
      than the last gate log (parallel pair: the integration gate log) (`find {{SOURCE_DIRS}} -newer <gate.log> -type f`); the Self-check answers every line of
      review-lessons-self-check.md (spot-check its claims).
   b. Re-run ONLY: the gate parts and suites your own edits touch; anything that failed, was skipped or rests on an unproven
      excuse (prove or disprove it, e.g. at BASE); the live checks of code you changed.
      Command: `{{PLAN_DIR}}/check.sh {{BASE}} <only what is needed> > <file> 2>&1`. Read the summary, and failures in full.
   c. If you edited nothing and the evidence is clean → "NOT RE-RUN — evidence verified: <log paths>".
   A gate pass is NOT the review.
4. FIX POLICY:
   - FIX YOURSELF every minor or medium finding that needs no design decision and touches fewer than ~15 files. With more than ~10
     non-trivial findings, fix only the small ones and hand the rest back. After your fixes, re-run what they touch (3b). List
     each fix with file:line and its batch.
   - Hand back ONLY findings that need a design decision, change behaviour beyond the brief, miss a whole brief item, or would
     touch ~15+ files. Write {{PLAN_DIR}}/{{BATCH_ID}}-fix1-brief.md in brief-template.md format, DECISIONS NEEDED at the top
     with your recommendation.
   - Never run git stash/checkout/restore/reset/add/commit. Format explicit files only.
5. Write {{PLAN_DIR}}/{{BATCH_ID}}-review-report.md in PLAIN WORDS (never bare ids): one line per checkpoint of
   review-checklist.md by its name, one line per performance group by its name, then one line per {{RULES_FILES}} section by its
   title. Each line: ✅ evidence / ❌ finding file:line / ⚠ accepted + reason / NOT RUN + why. Then "Fixed by reviewer"
   (file:line list), "Handed to implementer" (summary + fix brief path, or "none"), and whether your edits keep the A/B file sets
   disjoint (commit plan). Write it so a FRESH reviewer can verify every finding is closed.
6. Final message: VERDICT = PASS (everything fixed or nothing found, all gates green) or FIX ROUND NEEDED (fix brief written), plus
   the report path. Keep it short.

<!-- Batch brief template. The orchestrator copies it to <batch>-brief.md, fills every {{…}} and removes this comment.
Briefs answer EVERY decision in advance (files, names, shapes, error codes, indexes, settings keys, locale texts) but contain
no code: the implementer writes it, and the review checklist catches gaps. Re-check the brief against the current code
before EVERY dispatch. -->
<context — read first; you are a fresh session>
{{PROJECT_NAME}} ({{STACK_SUMMARY}}). BASE = {{BASE}} (tree clean except .superpowers/** — ignore it).
This batch {{BATCH_ID}} = {{ONE_LINE_SCOPE}} (plan {{PLAN_FILE}} phase {{PHASE}} task(s) {{TASKS}}).
OWNER RULES (binding): {{STANDING_OWNER_RULES — e.g. best practice without shortcuts and without over-engineering; never remove
shipped functionality the brief does not remove}}.
READ FIRST, IN FULL: {{RULES_FILES}}; {{PLAN_ABS}}/review-lessons-self-check.md; the plan phase {{PHASE}} task(s) {{TASKS}};
{{CONTRACT_SECTIONS_OR_NONE}}; {{SURVEY_PATH_AND_RULINGS}}.
</context>

<orchestrator_rulings — binding>
{{RULING_PREFIX}}-1 … one numbered ruling per work item: exact files to create/modify/delete, type and member names, shapes,
error codes + status, settings keys + example-config lines, indexes/migration name, locale texts in {{LANGUAGES}}, tests to
write with their exact names, and what NOT to touch.
</orchestrator_rulings>

<worktree — ONLY when this batch runs in its own git worktree (a PARALLEL pair); delete otherwise>
Your working tree is {{TREE}} (a git worktree on branch {{BRANCH}}, cut from {{BASE}}). Work ONLY there: never cd to or edit the main
checkout ({{REPO_ROOT}}); the only things you write outside {{TREE}} are the files in {{PLAN_ABS}}/runs/{{RUN}}/. Batch {{PARTNER_ID}}
runs AT THE SAME TIME in another worktree on files that are disjoint from yours: do not touch its files, and do not assume its code
exists. Make no commits and no branches (the orchestrator snapshots your tree). Dependencies are installed ({{WORKTREE_SETUP_CMD}});
if something is missing, list it under DECISIONS NEEDED instead of installing globally. You run the full gate on YOUR tree only; the
orchestrator gates the combined tree after both batches land.
{{PORTS_AND_SERVICES — ports, database, container names this batch may use, or none}}
</worktree>
<pair — ONLY for batch B of a SEQUENTIAL pair; delete otherwise>
Batch {{A_ID}} is implemented, unreviewed and uncommitted in the tree. Do not edit its files. If your change breaks one of
{{A_ID}}'s tests, update that test to the new contract and report it; never add a guard elsewhere to keep the old assertion
green. BASE for your gates = {{BASE}} (the commit before {{A_ID}}). You run the FULL gate on the combined tree.
</pair>
<pair-a — ONLY for batch A of a SEQUENTIAL pair; delete otherwise>
Batch B will run on top of your uncommitted work. Run only the focused gates listed below, never the long full gate.
</pair-a>

<hard_rules>
- NEVER run git commands that change files or the index ({{FORBIDDEN_GIT}}, add, commit). Format explicit FILES only. No
  background processes, servers or subagents except what the e2e gate starts. Gates run in the FOREGROUND.
- {{RULES_FILES}} exactly, including: functions ≤ {{FN_MAX_LINES}} lines with one job each (SOLID); no magic strings/numbers;
  every user-visible text in all locale files ({{LOCALE_FILES}}); generated migrations only through the framework generator,
  never hand-edited.
- Never delete or reset data (databases, volumes, files outside your diff). Stop that step and report it under DECISIONS NEEDED.
- If something contradicts the code or the rules, or is impossible: STOP that item, finish the rest, and list it under
  DECISIONS NEEDED with options + your recommendation.
</hard_rules>

<gates — foreground; output to files in the run folder; paste summaries VERBATIM (the reviewer verifies them against the logs)>
1. `cd "{{TREE}}" && CHECK_ROOT="{{TREE}}" "{{PLAN_ABS}}/check.sh" {{BASE}} {{GATE_OPTIONS}} > "{{PLAN_ABS}}/runs/{{RUN}}/gate.log" 2>&1` → ALL GATES PASS.
   ({{TREE}} = the repo root for a normal batch, your worktree for a parallel one.) This is your
   LAST step after every edit (no source file may be newer than gate.log). Paste its summary block verbatim.
2. {{EXTRA_PROOFS — zero-caller proofs for deletions, live calls for every new/changed endpoint or screen (request + response
   pasted verbatim), query plans for new hot queries}}. Save them to {{PLAN_ABS}}/runs/{{RUN}}/live-checks.log as you run them, and paste
   from that file.
3. `git -C {{TREE}} status --porcelain`.
</gates>

<report>
Your final message is the FULL report: per ruling, what changed (file:line) or the verification pointer; new/changed interfaces
with live-check evidence; migrations; settings keys (+ example lines); tests added (names + results); deleted symbols with proof;
DECISIONS NEEDED; a Self-check answering EACH line of review-lessons-self-check.md separately; gate tails. Do not commit.
</report>

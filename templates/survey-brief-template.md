<!-- Phase survey brief (READ-ONLY run). The orchestrator copies it to <phase>-survey-brief.md and fills {{…}}. The output
becomes runs/<phase>-survey.md; the orchestrator appends ORCHESTRATOR RULINGS + BATCH ORDER at its end. -->
<context — read first; you are a fresh session, READ-ONLY>
{{PROJECT_NAME}} ({{STACK_SUMMARY}}). BASE = {{BASE}}. You SURVEY phase {{PHASE}} of {{PLAN_FILE}} before any code is written.
Change nothing.
READ FIRST, IN FULL: {{RULES_FILES}}; the plan (global constraints, review focus, phase {{PHASE}}); {{CONTRACT_SECTIONS_OR_NONE}}.
</context>

<survey>
For EVERY task of phase {{PHASE}}, write:
1. Current code map: every file/type/member/endpoint/screen/table/job/setting the task touches, with file:line; every consumer
   that ripples (other features, jobs, tests, e2e suites, other apps).
2. Delta: exactly what changes (create/modify/delete per file), migrations, settings keys, locale keys ({{LANGUAGES}}), tests.
3. Risks: concurrency, performance on large data, security/privacy, contract mismatches, behaviour that must be kept, and
   rules-file violations in code that will be touched (functions over {{FN_MAX_LINES}} lines, multi-type files, missing comments).
4. Open questions / decisions with options + your recommendation (the orchestrator rules on them).
5. A proposed BATCH ORDER: batches of ≈ {{BATCH_MINUTES}} minutes, each marked MECHANICAL or JUDGEMENT, with dependencies,
   disjoint-file PAIR suggestions, and the e2e/live checks each batch must run.
</survey>

<hard_rules>
READ-ONLY: do not edit, create or delete any file except your final message. No git commands that change anything. No builds
that write outside the build output folders. No containers.
</hard_rules>

<report>
Your final message is the full survey in markdown (one section per task, then "Open questions", then "Proposed batch order").
</report>

# SDD ledger — {{PLAN_TITLE}}
> Plan: {{PLAN_FILE}} · Rules: {{RULES_FILES}} · Contract/spec: {{CONTRACT_DOCS}}
> After a context compaction: read ORCHESTRATOR_HANDOFF.md in this folder first.

## Roadmap (tick ✅ only at a phase close-out, after the fresh full verification)
| Phase | Scope | Status | Where |
| --- | --- | --- | --- |
| P0 | <scope> | ⬜ | {{WORK_BRANCH}} |

Status marks: ⬜ not started · 🔄 in progress · ✅ closed (date, close-out commit).

## Ledger
One line per event: dispatch, review verdict, ruling batch, owner decision, commit, lane switch, lesson. Newest last.
Format: `- <date> (s<N>) — <batch ids> <EVENT>: <what> (<commit / report path>; rulings <ids>; review cost <tokens/tools/min>)`.
Closed phases move to archive-progress-through-s<N>.md, leaving a two-line summary here.

- {{TODAY}} (s1) — SETUP: es-orchestrator scaffold created ({{PLAN_DIR}}); profiles {{PROFILE_NAMES}}; baseline gate → runs/baseline/gate.log.

# es-orchestrator

A [Claude Code](https://claude.com/claude-code) skill that runs a long implementation plan with Claude as
**orchestrator only**. Claude writes surveys, briefs and rulings. Cheaper implementer models write the code in
paired ≈30-minute batches. A fresh reviewer agent checks every pair line by line against stack checklists. You get
the full review report before every commit, and a handoff file, a progress ledger and a next-session prompt carry
the state across sessions and context compactions.

It is stack- and business-agnostic. The stack is detected from the repo (backend, mobile or web, monorepos
included). The coding rules ship as defaults that you keep, edit or replace during setup.

## Why

- Summary-only reviews miss defects. Here every changed line is read against a written checklist, with evidence.
- Cheap implementers fabricate gate output. Here evidence is verified against log files, and the gate must be newer
  than every source file before a commit.
- Long sessions lose state. Here an END STATE block, a ledger and a generated resume prompt make every session
  restartable.
- Big batches overwhelm reviews. Here batches take ≈30 minutes, run as pairs, with one review per pair.

## Install

```bash
git clone <this repo> ~/.claude/skills/es-orchestrator
```

Requirements: `bash`, `git` and `python3` (standard library only). Delegate skills for implementer lanes are
optional (any of `claude-delegate`, `opencode-delegate`, `cursor-delegate`, `agy-delegate`, `codex-delegate`, …);
without them the plain Agent tool is the fallback lane.

## Use

**Set up a project** (once per plan):
```
Use es-orchestrator to set up the orchestrator workflow for this repo: plan = docs/plans/my-plan.md
```
Claude detects the stack, shows what it found, and asks only for the rest: coding rules (defaults / edit /
replace / repo file only), gate commands, implementer lanes, reviewer model, batch size, languages and staging
paths. It then generates `.superpowers/sdd/<PLAN_ID>/` and runs a baseline gate.

**Resume** (every new session): paste the generated `NEXT_SESSION_PROMPT.md`, or:
```
Use es-orchestrator to continue <PLAN_ID> as ORCHESTRATOR.
```

**End a session**:
```
Use es-orchestrator to end the session: write the END STATE, the next-session prompt, and trim the archives.
```

## What gets generated

```
.superpowers/sdd/<PLAN_ID>/
  ORCHESTRATOR_HANDOFF.md      commit gate, roles, LIVE STATUS / END STATE, decisions, rule checklist, workflow
  progress.md                  roadmap + one ledger line per review/commit
  coding-rules.md              the rules implementers and reviewers follow (defaults / edited / your own)
  review-checklist.md          mandatory review checkpoints (generic + stack)
  performance-checklist.md     performance groups for the stack
  review-lessons-self-check.md implementer self-check; grows with every review finding
  brief / survey / review-full / review-light templates, reviewer-agent.md, NEXT_SESSION_PROMPT.md
  check.sh + fnlen.py + locale_parity.py + allow-lists + forbidden-patterns.txt + gates.d/
  runs/<batch>/                START marker, result.json, REPORT.md, gate.log, live-checks.log
```

## Layout of this skill

| Path | What |
| --- | --- |
| `SKILL.md` | Mode router (setup / session loop / end of session) and the non-negotiables |
| `references/` | Setup flow, answers schema, session loop, end-of-session, lanes, pairing & review, git & gates, owner decisions |
| `templates/` | Files copied into the plan folder |
| `profiles/{generic,backend,mobile,web}/` | Coding rules, review checkpoints, performance checklist, self-check lines, defaults, gate hooks, gate snippets |
| `scripts/detect_stack.py` | Suggests profiles, gate commands, locale/rules/plan files from the repo |
| `scripts/scaffold.py` | Generates the plan folder from `answers.json` |
| `scripts/status.py` | Exact done/left % (by count and effort), phases, running runs |
| `scripts/archive.py` | End-of-session trimming of the handoff and the ledger |

## Customize

- **Rules**: edit `profiles/<stack>/coding-rules.md`, or choose "edit"/"replace" during setup.
- **A new stack**: add `profiles/<name>/` with the same six files. `generic` is always the base.
- **More gates**: drop a snippet into `profiles/<stack>/gate-snippets/` (it is sourced by `check.sh`; `pre-*`
  snippets run before the build).

## License

MIT. See [LICENSE](LICENSE).

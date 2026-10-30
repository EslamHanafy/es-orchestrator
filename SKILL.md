---
name: es-orchestrator
description: >-
  Orchestrator-only delivery workflow for any project and stack. Claude writes surveys, briefs and rulings; cheap implementer lanes write the code in ~30-minute batches (pairs, optionally in parallel git worktrees); a fresh reviewer agent reads every changed line; the owner gets the full report before every commit; a handoff file and a progress ledger carry state across sessions. Use it to set up the workflow, to continue a plan ("continue as orchestrator", "read the handoff END STATE", or any repo with .superpowers/sdd/*/ORCHESTRATOR_HANDOFF.md), to end a session with an END STATE block, or to run ONE step only: "plan only", "orchestrate only", "review only", "commit only" or the "full cycle".
metadata:
  version: "1.1.0"
---

# es-orchestrator

A reusable process for running a long implementation plan with Claude as **orchestrator only**. It does not depend
on the business domain or the stack. Stack knowledge sits in `profiles/<stack>/` (backend, mobile, web, generic) and
in the project's own gate script. The stack is detected from the repo, and the coding rules are defaults that the
owner keeps, edits or replaces during setup.

Why this shape: summary-only reviews miss defects. Cheap implementers fake evidence. Long sessions lose state on
compaction. Each rule below is the fix for one of those failures. When a rule feels heavy, keep it and record the
reason in the decisions table rather than dropping it on your own.

## Where the skill lives (`$ES`)

Scripts are referenced as `$ES/scripts/...`. `$ES` is the directory this SKILL.md was loaded from. It depends on
how the skill was installed: `~/.claude/skills/es-orchestrator`, `<project>/.claude/skills/es-orchestrator`,
`~/.agents/skills/es-orchestrator` or `<project>/.agents/skills/es-orchestrator` (`npx skills add` uses the last
two as its canonical copy and symlinks the agent folders to it). Use the base directory that the skill loader gave
you. If you were not given one, run
`ls -d ~/.claude/skills/es-orchestrator .claude/skills/es-orchestrator ~/.agents/skills/es-orchestrator .agents/skills/es-orchestrator 2>/dev/null | head -1`.
Shell variables do not persist between calls, so write the resolved absolute path into each command.
`python3 $ES/scripts/doctor.py --repo . [--plan-id <ID>]` checks the install and a plan folder (tools, delegate skills,
files, placeholders, gitignore, reviewer agent, stale runs, leftover worktrees).

## Host requirements and fallbacks

Built for Claude Code. It uses these tools; when one is missing, use the fallback instead of stopping:

| Needs | Fallback |
| --- | --- |
| `AskUserQuestion` (setup interview, owner decisions) | Ask the same question in plain chat, recommendation first, and wait |
| `SendUserFile` (full report to the owner) | Print the report's absolute path and offer to paste it; still `touch` the OWNER_REPORT_SENT marker once they have it |
| `Agent` tool with `subagent_type` (fresh reviewer, survey helper) | Run the reviewer through a delegate lane with the strongest model, in a NEW session, with the same review prompt |
| `run_in_background` + completion notification | Run the command detached (`nohup … &`, pid file) and wait on the pid; never poll the log |
| A delegate skill (claude-/opencode-/cursor-/agy-/codex-delegate …) | The plain Agent-tool lane (`references/lanes.md`) |

## Pick the mode

| The user wants… | Mode | Read |
| --- | --- | --- |
| A new project/plan set up | **Setup** (quick path or full interview) | `references/setup-flow.md` |
| Only the planning: surveys, rulings, batch order, briefs | **`plan`** | `references/run-modes.md` |
| Only the implementation: dispatch the pair from ready briefs (sequential or parallel) | **`orchestrate`** | `references/run-modes.md`, `references/parallel-pairs.md` |
| Only a review of a finished pair, plus the owner report | **`review`** | `references/run-modes.md` |
| Only the gate, the commit and the bookkeeping for a reviewed pair | **`commit`** | `references/run-modes.md` |
| To continue an existing plan end to end (a handoff exists) | **`full`** (the session loop, default) | `references/session-loop.md` |
| Done/left %, stage, what is running | **Status** | run `$ES/scripts/status.py`, report in plain words |
| To stop for today / "write the end state" | **End of session** | `references/end-of-session.md` |

The user can name the mode in words ("plan only", "just review B14+B15"), with a keyword (`mode: review`) or as the
skill argument (`/es-orchestrator review B14+B15`), and can add `parallel` or `sequential` for the pair. A bare
"continue" is `full`. If the request is vague, ask which mode with `full` as the recommended option. A single-step
mode runs only its own stage, records the stage reached (`status.py --set-stage`), ends by naming the next mode, and
never relaxes a rule of the stages it keeps (`references/run-modes.md`).

If `.superpowers/sdd/*/ORCHESTRATOR_HANDOFF.md` already exists in the repo, a "continue" request is `full`. If it
does not exist, no mode but Setup can run: say so and offer Setup.

## Roles (do not blur them)

- **Owner** (the user): decides product, scope, money, security and data-loss trade-offs, and anything a ruling
  reserves to them. Gets the full review report before every commit.
- **Orchestrator** (you): surveys, briefs, rulings, batch order and dispatch. Reads the reviewer's report and owns
  the verdict. Runs the gate, commits and keeps the books. You write feature code only for tiny follow-ups that a
  reviewer handed back and that need no design decision.
- **Implementer lanes**: cheap models in their own sessions, one batch each (`references/lanes.md`).
- **Reviewer**: a fresh, strong-model subagent for each pair. It fixes minor findings itself and hands the rest
  back as a fix brief (`references/pairing-and-review.md`).

## Setup (summary; details in references/setup-flow.md)

1. **Detect** the stack: `python3 $ES/scripts/detect_stack.py <repo>` suggests profiles (backend / mobile / web), gate
   commands, locale files, rules files and plan candidates. **Quick path:** add `--draft-answers` for a complete
   `answers.json` draft plus a `_confirm` list, and ask the owner once: use the draft / walk through everything / change a few.
2. **Interview** (AskUserQuestion, max 4 questions per round, recommended option first) only for what detection could
   not settle: plan id and file, **coding rules** (defaults / edit / replace / repo file only), gate commands and snippets,
   gate timeout, function-length limit, implementer lanes with fallbacks, reviewer model/effort and where its agent is
   installed, batch size, languages, staging paths, **parallel pairs** (`auto`/`off`, worktree setup command, files to copy),
   and owner-reserved decision categories.
3. Write `answers.json` (schema: `references/answers-schema.md`), then
   `python3 $ES/scripts/scaffold.py --answers answers.json --repo <repo root>`.
   It validates `PLAN_ID` and warns about unknown keys, creates `.superpowers/sdd/<PLAN_ID>/` from `templates/` plus the
   chosen profiles, and lists every placeholder it could not fill. For a plan created by an older version, add the new
   helper scripts with `scaffold.py --upgrade-static --repo <repo> --plan-id <ID>`.
4. Fill the leftovers by hand. Wire the stack hooks in `check.sh`. Install the reviewer agent from `reviewer-agent.md`
   (default: the project's `.claude/agents/`; ask first). Confirm that `.superpowers/` is gitignored. Run `doctor.py`.
5. Run the gate once on HEAD and record it as the **baseline** (known failures, legacy debt counts).
6. Record the setup answers as decisions O-1… in the handoff. Write `NEXT_SESSION_PROMPT.md` and show it to the
   owner. Then start the first survey.

## Session loop = `full` mode (summary; details in references/session-loop.md)

Stages: **plan** = steps 1–4, **orchestrate** = step 5, **review** = steps 6–7, **commit** = steps 8–9. Step 10 is
the rhythm of `full`. Each single-step mode runs just its stages (`references/run-modes.md`).

1. **Resume**: read the handoff END STATE / LIVE STATUS, RULE CHECKLIST, ROLES and DECISIONS. Then read the tail of
   `progress.md`, the self-check, and only the survey files the next step needs.
2. **Status first**: run `scripts/status.py` and give the owner done/left % (by count and by effort), the stage, what is
   running, and what comes next.
   Then ask any open OWNER-REVIEW items.
3. **Rule implementer DECISIONS** yourself, with a reason, and record them. Send only owner-reserved ones to the
   owner, together with your recommendation (`references/owner-decisions.md`).
4. **Re-check the brief against the current code** before every dispatch (BASE, file:line facts, rulings), and
   update it first.
5. **Dispatch the pair.** Sequential: A, then B on top of the uncommitted A. **Parallel** (survey tag `PARALLEL-OK`,
   `PARALLEL_PAIRS` not `off`, previous pair committed): A and B at the same time in git worktrees, then landed together
   and gated on the combined tree (`references/parallel-pairs.md`). Either way: a new implementer session per batch, in the
   background, never poll.
6. **Fresh reviewer** for the pair. Read its report and own the verdict. For a fix round, use the same lane, then
   a NEW reviewer.
7. **Send the full report file** (SendUserFile) plus a plain-language summary to the owner, then `touch` the pair's
   OWNER_REPORT_SENT marker.
8. **Gate freshness**: the gate has passed on HEAD and no source file is newer than the gate log. If either is not
   true, re-run the gate (`references/git-and-gates.md`).
9. **Commit** with explicit-path staging. Then do the **bookkeeping**: ledger line, LIVE STATUS, plan status line,
   and a review-usage line.
10. In `full` mode keep dispatching until the owner says stop (a single-step mode stops after its stage). Walk the
    RULE CHECKLIST before every brief, dispatch, ruling and commit.

## End of session (summary; details in references/end-of-session.md)

Write the **END STATE** block at the top of LIVE STATUS: progress %, stage and next mode, branches/HEADs, what is
running or uncommitted, live worktrees, NEXT in order, lanes, and lessons. Rewrite `NEXT_SESSION_PROMPT.md` (back up
the old one first). Run `scripts/archive.py` (a dry run, then `--apply`) to move stale session blocks and old ledger
lines into `archive-*-through-s<N>.md`, so the handoff stays short. Give the owner the resume prompt in chat.

## Non-negotiables (and why)

- **No commit before the owner has the full report file and every finding is fixed.** This includes findings in
  old code inside touched files. The owner is the last line of defence and cannot judge from a summary.
- **A gate pass is not a review.** The reviewer reads every changed line (FULL) or the proofs plus ≥15 sampled
  hunks (LIGHT, mechanical batches only).
- **Evidence first, no blind re-runs.** Implementers paste gate output verbatim from log files. The reviewer
  verifies it and re-runs only what it touched or what is doubtful. Fabricated counts are a known failure mode.
- **Never stash, checkout, restore, reset, or switch branches** in a shared tree. Never edit generated migrations
  or the database by hand. Stage explicit paths only. Only the orchestrator creates or removes worktrees, and only
  through `scripts/worktree.py`.
- **Batches take about BATCH_MINUTES (default 30).** Split before dispatch. Ask the owner if a batch truly cannot
  be split.
- **Report wording in plain words.** Never send bare checklist ids ("C17") to the owner.

## Files in this skill

- `references/` — setup-flow, answers-schema, run-modes, parallel-pairs, session-loop, end-of-session, lanes,
  pairing-and-review, git-and-gates, owner-decisions.
- `templates/` — copied into the project by `scaffold.py`: handoff, progress, briefs, review prompts, self-check,
  decisions table, next-session prompt, reviewer agent, gate skeleton and its helpers (`run_timeout.py`,
  `scan_added.py`, `fnlen.py`, `locale_parity.py`), allow-lists, secret patterns.
- `profiles/{generic,backend,mobile,web}/` — default coding rules, review checkpoints, performance checklist, extra
  self-check lines, defaults, gate hook notes, and optional `gate-snippets/` for each stack.
- `scripts/` — `detect_stack.py` (profiles, commands, quick-setup draft), `scaffold.py` (generates the project folder
  from `answers.json`), `status.py` (done/left %, stage, runs), `worktree.py` (parallel pairs), `archive.py`
  (end-of-session trimming), `doctor.py` (health check).
- `tests/` — `python3 -m unittest discover -s tests` (the CI runs it on Linux and macOS).

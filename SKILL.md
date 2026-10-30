---
name: es-orchestrator
description: >-
  Sets up and runs the "orchestrator-only" delivery workflow on any project and any stack. Claude writes surveys, briefs and rulings; cheap implementer lanes write the code in ≈30-minute batches run as pairs; a fresh reviewer agent checks every pair line by line against stack checklists; the owner gets the full report before every commit. A handoff file, a progress ledger and a next-session prompt carry state across sessions. Use this whenever the user asks to "set up the orchestrator workflow", "use es-orchestrator", wants a handoff + progress + lanes + paired-review process for a plan, says "continue as orchestrator" / "resume the revamp" / "read the handoff END STATE", or asks to end an orchestrator session with an END STATE block. Also use it when a project already has an ORCHESTRATOR_HANDOFF.md under .superpowers/sdd/ and the user wants to keep going, even if they don't name the skill. It can run a single step on its own: "plan only" (surveys, rulings, briefs), "orchestrate only" (dispatch the implementers), "review only" (fresh reviewer and owner report), "commit only" (gate, commit, books), or the "full cycle" (default).
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

## Pick the mode

| The user wants… | Mode | Read |
| --- | --- | --- |
| A new project/plan set up | **Setup** | `references/setup-flow.md` |
| Only the planning: surveys, rulings, batch order, briefs | **`plan`** | `references/run-modes.md` |
| Only the implementation: dispatch the pair from ready briefs | **`orchestrate`** | `references/run-modes.md` |
| Only a review of a finished pair, plus the owner report | **`review`** | `references/run-modes.md` |
| Only the gate, the commit and the bookkeeping for a reviewed pair | **`commit`** | `references/run-modes.md` |
| To continue an existing plan end to end (a handoff exists) | **`full`** (the session loop, default) | `references/session-loop.md` |
| Done/left % and what is running | **Status** | run `$ES/scripts/status.py`, report in plain words |
| To stop for today / "write the end state" | **End of session** | `references/end-of-session.md` |

The user can name the mode in words ("plan only", "just review B14+B15"), with a keyword (`mode: review`) or as the
skill argument (`/es-orchestrator review B14+B15`). A bare "continue" is `full`. If the request is vague, ask which
mode with `full` as the recommended option. A single-step mode runs only its own stage, ends by naming the next
mode, and never relaxes a rule of the stages it keeps (`references/run-modes.md`).

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

1. **Detect** the stack: run `scripts/detect_stack.py <repo>`. It suggests profiles (backend / mobile / web),
   gate commands, locale files, rules files and plan candidates. The owner confirms or overrides each one.
2. **Interview** the owner (AskUserQuestion, max 4 questions per round, recommended option first) only for what
   detection could not settle. That covers: plan id, plan file, **coding rules** (use the defaults / edit them /
   replace them with their own / the repo rules file only), gate commands and extra gate snippets,
   function-length limit, implementer lanes with fallbacks, reviewer model/effort, batch size, languages,
   staging paths, and owner-reserved decision categories.
3. Write the answers to `answers.json` (schema: `references/answers-schema.md`). Then run:
   `python3 $ES/scripts/scaffold.py --answers answers.json --repo <repo root>`
   It creates `.superpowers/sdd/<PLAN_ID>/` from `templates/` plus the chosen profiles, and lists every
   placeholder it could not fill.
4. Fill the leftovers by hand. Wire the stack hooks in `check.sh`. Install the reviewer agent from
   `reviewer-agent.md` into `~/.claude/agents/` (ask first, since that is user-level config). Confirm that
   `.superpowers/` is gitignored.
5. Run the gate once on HEAD and record it as the **baseline** (known failures, legacy debt counts).
6. Record the setup answers as decisions O-1… in the handoff. Write `NEXT_SESSION_PROMPT.md` and show it to the
   owner. Then start the first survey.

## Session loop = `full` mode (summary; details in references/session-loop.md)

Stages: **plan** = steps 1–4, **orchestrate** = step 5, **review** = steps 6–7, **commit** = steps 8–9. Step 10 is
the rhythm of `full`. Each single-step mode runs just its stages (`references/run-modes.md`).

1. **Resume**: read the handoff END STATE / LIVE STATUS, RULE CHECKLIST, ROLES and DECISIONS. Then read the tail of
   `progress.md`, the self-check, and only the survey files the next step needs.
2. **Status first**: run `scripts/status.py` and give the owner done/left % (by count and by effort), what is
   running, and what comes next.
   Then ask any open OWNER-REVIEW items.
3. **Rule implementer DECISIONS** yourself, with a reason, and record them. Send only owner-reserved ones to the
   owner, together with your recommendation (`references/owner-decisions.md`).
4. **Re-check the brief against the current code** before every dispatch (BASE, file:line facts, rulings), and
   update it first.
5. **Dispatch pair A**, then **pair B** on top of the uncommitted A. Use a new implementer session per batch, run
   in the background, and never poll.
6. **Fresh reviewer** for the pair. Read its report and own the verdict. For a fix round, use the same lane, then
   a NEW reviewer.
7. **Send the full report file** (SendUserFile) plus a plain-language summary to the owner.
8. **Gate freshness**: the gate has passed on HEAD and no source file is newer than the gate log. If either is not
   true, re-run the gate (`references/git-and-gates.md`).
9. **Commit** with explicit-path staging. Then do the **bookkeeping**: ledger line, LIVE STATUS, plan status line,
   and a review-usage line.
10. Keep dispatching until the owner says stop. Walk the RULE CHECKLIST before every brief, dispatch, ruling and
    commit.

## End of session (summary; details in references/end-of-session.md)

Write the **END STATE** block at the top of LIVE STATUS: progress %, branches/HEADs, what is running or
uncommitted, NEXT in order, lanes, and lessons. Rewrite `NEXT_SESSION_PROMPT.md` (back up the old one first).
Run `scripts/archive.py` (a dry run, then `--apply`) to move stale session blocks and old ledger lines into
`archive-*-through-s<N>.md`, so the handoff stays short. Give
the owner the resume prompt in chat.

## Non-negotiables (and why)

- **No commit before the owner has the full report file and every finding is fixed.** This includes findings in
  old code inside touched files. The owner is the last line of defence and cannot judge from a summary.
- **A gate pass is not a review.** The reviewer reads every changed line (FULL) or the proofs plus ≥15 sampled
  hunks (LIGHT, mechanical batches only).
- **Evidence first, no blind re-runs.** Implementers paste gate output verbatim from log files. The reviewer
  verifies it and re-runs only what it touched or what is doubtful. Fabricated counts are a known failure mode.
- **Never stash, checkout, restore, reset, or switch branches** in a shared tree. Never edit generated migrations
  or the database by hand. Stage explicit paths only.
- **Batches take about BATCH_MINUTES (default 30).** Split before dispatch. Ask the owner if a batch truly cannot
  be split.
- **Report wording in plain words.** Never send bare checklist ids ("C17") to the owner.

## Files in this skill

- `references/` — setup-flow, answers-schema, run-modes, session-loop, end-of-session, lanes, pairing-and-review,
  git-and-gates, owner-decisions.
- `templates/` — copied into the project by `scaffold.py`: handoff, progress, briefs, review prompts, self-check,
  decisions table, next-session prompt, reviewer agent, gate skeleton, allow-lists.
- `profiles/{generic,backend,mobile,web}/` — default coding rules, review checkpoints, performance checklist, extra
  self-check lines, defaults, gate hook notes, and optional `gate-snippets/` for each stack.
- `scripts/` — `detect_stack.py` (suggests profiles and commands), `scaffold.py` (generates the project folder
  from `answers.json`), `status.py` (exact done/left %), `archive.py` (end-of-session trimming).

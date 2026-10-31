# Session loop (resume → dispatch → review → commit → books)

`$W` = `.superpowers/sdd/<PLAN_ID>` below. `$ES` = the skill's own directory (see SKILL.md).

This file is the `full` mode. Single-step modes run a slice of it: plan = §1–4, orchestrate = §5, review = §6–7,
commit = §8–9 (`run-modes.md`).

## 1. Resume

Read, in this order and only as far as you need:
1. `$W/ORCHESTRATOR_HANDOFF.md`: the newest END STATE / LIVE STATUS block, then HARD GATE, ROLES, RULE CHECKLIST
   and DECISIONS (newest rows).
2. The tail of `$W/progress.md` (this and the last session).
3. `$W/review-lessons-self-check.md`. Every brief embeds it.
4. Only the survey/fact files that the NEXT item names. Archives are for archaeology only.

Check reality against the handoff: `git log -3`, `git status --porcelain`, running relay or gate processes
(`ps -ef | grep -E "relay|check.sh"`), and `runs/<id>/result.json` of anything marked RUNNING. If they differ,
reality wins. Write one ledger line saying what you found.

## 2. Status first

Before any work, run `python3 $ES/scripts/status.py --repo . --plan-id <PLAN_ID>` and
tell the owner in plain words:
- done / left as % by task count **and** by effort (from status.py; tag plan tasks `[S]`/`[M]`/`[L]`/`[XL]` or
  `[effort: N]` to get real effort weights), plus the phases closed and the phase open;
- what is running or uncommitted;
- NEXT, in order;
- open OWNER-REVIEW items (decisions you took that the owner should confirm or reverse). Ask them now with
  AskUserQuestion, recommendation first.

Then keep going without waiting, unless an answer blocks the next step.

## 3. Rule the DECISIONS

Each implementer REPORT ends with DECISIONS NEEDED. For each one:
- Owner-reserved (`owner-decisions.md`)? Then ask the owner with options and a recommendation, record the answer
  as O-n, and park the dependent work.
- Otherwise rule it yourself. Record it as `<PHASE>-R<n>` in the survey/rulings file with the reason, list it in
  the next owner summary, and check that it does not contradict any O-row.

## 4. Brief, re-checked

- New brief: copy `brief-template.md`, answer every decision in advance (files, names, shapes, errors, settings,
  locale texts, test names, what NOT to touch), and add no code snippets.
- **Before every dispatch**, re-check an older brief against the current code: BASE commit, file:line facts, newer
  rulings, and files a previous batch already changed. Update the brief first. Stale briefs are the biggest
  source of wasted runs.
- Size check: files × complexity ≈ BATCH_MINUTES. Over by more than ~15% → split now.

## 5. Dispatch the pair

- **A wave of lanes?** A large set of independent batches can run as up to 4 parallel lanes on worktree tracks
  (`parallel-lanes.md`); each lane then runs this loop on its own track.
- **Parallel or sequential?** If the survey tags the pair `PARALLEL-OK`, `PARALLEL_PAIRS` is not `off` and the previous pair is
  committed, run A and B at the same time in git worktrees (`parallel-pairs.md`) and continue at §6 once they are landed and the
  integration gate has run. Otherwise use the sequential steps below.
- A: `mkdir -p $W/runs/<A>; touch $W/runs/<A>/START`, then the lane command with `run_in_background`. Do not poll;
  wait for the completion notification.
- A's brief must not start a long full gate, because B will edit during it. A runs focused gates; B runs the full
  gate on the combined tree.
- When A finishes: save the report verbatim to `runs/<A>/REPORT.md`. Check its completeness (per-ruling list,
  DECISIONS, every self-check line). If anything is missing, do a report-only resume turn on the same session.
- B: `touch $W/runs/<B>/START` (the file-ownership marker), then dispatch B with the PAIR block filled.
- Quota or usage-limit error: switch at once to the lane's fallback with the same brief, and tell the owner in one
  line. Never restart an interrupted run; **resume** it on its session with a short delta brief.

## 6. Review

- Copy `review-full-template.md` (or `review-light-template.md` for a MECHANICAL batch). Fill it and save it as
  `review-<A>+<B>-prompt.md`.
- Agent tool: `subagent_type: <REVIEWER_AGENT>`, `model: <REVIEWER_MODEL>`, background.
- The reviewer writes `<A>+<B>-review-report.md`, and `<id>-fix1-brief.md` if one is needed.
- Read the whole report, spot-check two or three findings yourself, and own the verdict.
- FIX ROUND NEEDED: same implementer lane, resumed on its session, then a NEW fresh reviewer that is given the
  previous report. Cycle 2+ re-runs only what the fix touched.
- Log the review cost (tokens, tool calls, minutes) in the ledger.

## 7. Owner report

`SendUserFile` the full report file (then `touch $W/<A>+<B>-OWNER_REPORT_SENT`), plus a plain-language summary in chat: what changed, what the reviewer
fixed, what was handed back, rulings you made, and anything NOT RUN. Use plain checkpoint names, never bare ids.

## 8. Gate freshness, then commit

See `git-and-gates.md`. In short: the gate passed on the tree being committed **and**
`find <SOURCE_DIRS> -newer runs/<B>/gate.log -type f` is empty. Then stage explicit paths, commit, and verify
with `git status`.

## 9. Bookkeeping (same turn as the commit)

- `progress.md`: one ledger line (date, session, batch ids, commit, reviewer verdict, rulings, review cost).
- Handoff LIVE STATUS: replace the session line. Do not append forever.
- Plan file: the task's Status line and the phase row's commit list, in the same commit. Every deferral gets a
  dated `ADDED YYYY-MM-DD:` line.
- New defect class found by the review → append a line to `review-lessons-self-check.md`.

## 10. Rhythm

- In `full` mode do not stop between batches (a single-step mode stops after its own stage). Write the next pair's briefs while a review runs.
- One chat line per milestone (dispatched, review verdict, committed).
- Walk the RULE CHECKLIST before every brief, dispatch, ruling and commit. It exists because each of its lines
  was broken once.
- Before big strong-model jobs (phase close-out verifications, multi-batch sweeps), tell the owner first.
- Phase close-out: a fresh FULL review over the whole phase diff. Then tick the roadmap row and write a
  next-session prompt.
- Plan finished: clean up, then the **final whole-task review** (`pairing-and-review.md`), its fixes, the final gate, and only
  then the END STATE.
- **Tooling changes** (gate, helpers, compose, proxy) follow code discipline: one step at a time with its proof log, then a
  fresh strong-model review of the tooling diff before any gate relies on it (`shared-stack.md` §9).

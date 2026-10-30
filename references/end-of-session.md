# End-of-session ritual

Trigger: the owner says stop, a usage limit is near, or the context is long and a fresh session would be cheaper.
If a task is running, either let it finish (when the owner said "stop after the running task") or record it as
RUNNING with its pid, out-dir and session id.

## 1. END STATE block (top of LIVE STATUS in the handoff)

Back up first: `cp ORCHESTRATOR_HANDOFF.md ORCHESTRATOR_HANDOFF.md.bak-<date>s<N>`. Then write:

```
**▶▶ SESSION <N> END STATE (<date>; <why it stopped>) — RESUME HERE FIRST:**
- PROGRESS: ≈ <done>/<total> plan tasks ✅ (≈ <x> % by count, ≈ <y> % by effort). PHASES CLOSED: … OPEN: …
- BRANCHES: <branch> <short sha> = <what>; worktree tracks and their state; merge-gate counter.
- COMMITS THIS SESSION: <sha> <batch> · …  Rulings <range> (where). Owner decisions O-<a>…O-<b>.
- AT STOP: what is RUNNING (pid, out-dir, session id) or FINISHED-UNCOMMITTED (report path, open DECISIONS).
- OWNER-REVIEW ITEMS: decisions you took that the owner must confirm or reverse (one line each).
- NEXT (in order): 1. … 2. … (brief written? BASE? pair partner?)
- LANES: current lane order and any quota reset dates.
- LESSONS: what went wrong this session and the rule that prevents it (also add it to the RULE CHECKLIST or the
  self-check if it is general).
```

Replace the previous session's LIVE line. Do not stack them. Old END STATE blocks move to the archive (step 3).

## 2. NEXT_SESSION_PROMPT.md

Back it up as `NEXT_SESSION_PROMPT.md.bak-<date>s<N>`, then rewrite it from `templates/NEXT_SESSION_PROMPT.md`:
- the read order (END STATE, RULE CHECKLIST, ROLES, newest decisions, checklists, progress tail, the specific
  survey/fact files);
- STATE in two or three lines (HEADs, what is uncommitted, what is running);
- FIRST: status with done/left %, then the open owner items, then NEXT;
- LANES, with the exact commands or a pointer to the handoff;
- STANDING RULES that bit this project (keep them short; the handoff has the full list).

Give the owner the prompt **in chat** as well. It is what they paste into the next session.

## 3. Archive trimming (keep the handoff readable)

Run `python3 $ES/scripts/archive.py --repo . --plan-id <PLAN_ID> --session <N>` as a
dry run, check the counts, then repeat it with `--apply`. It backs up both files and moves the old LIVE STATUS
blocks and the ledger lines older than the last two sessions. Do the rest by hand:

Aim: handoff ≲ 400 lines, progress ≲ 300 lines of live ledger.
- Move superseded session blocks, per-phase histories and old LIVE lines into
  `archive-ORCHESTRATOR_HANDOFF-through-s<N>.md`. Leave a one-line pointer where they were.
- Move ledger lines of closed phases into `archive-progress-through-s<N>.md`. Leave a two-line summary in
  progress.md.
- Never archive: HARD GATE, ROLES, DECISIONS table, RULE CHECKLIST, workflow, key paths, checklists.
- Superseded decisions stay in the table with `superseded by O-n`. Do not delete them.

## 4. Last checks

- `git status`: nothing of yours left unstaged by accident. Everything uncommitted is named in END STATE.
- No background process of yours left running unless END STATE names it.
- Memory: if a cross-project lesson emerged (a workflow preference, a tool gotcha), save it to user memory, not
  only the handoff.

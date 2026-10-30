# Run modes (one step, or the whole cycle)

The session loop in `session-loop.md` has five stages. Each stage can be run on its own, or you can run all of
them. The owner picks the mode in plain words ("plan only", "just review A+B"), with a keyword
("mode: review"), or as the skill argument (`/es-orchestrator review A+B`).

```
 plan ──▶ orchestrate ──▶ review ──▶ commit
   └──────────────── full ─────────────┘   (all four, repeated until the owner stops)
```

| Mode | Stage(s) of the loop | Starts from | Stops when | Never does |
| --- | --- | --- | --- | --- |
| `plan` | 1–4: resume, status, rule DECISIONS, write and re-check briefs | A plan file and a `$W` folder | Briefs are written, re-checked and the batch order is shown | Dispatch an implementer, review, commit |
| `orchestrate` | 5: dispatch pair A then B | Briefs that exist and pass the re-check | Both reports are saved in `runs/<id>/REPORT.md` and checked for completeness | Review, commit |
| `review` | 6–7: fresh reviewer, owner report | A finished pair in the working tree (or a commit range) | The report file and the plain-language summary are with the owner | Dispatch a new batch, commit |
| `commit` | 8–9: gate freshness, commit, bookkeeping | A reviewed pair with every finding fixed | Commit done and the books updated | Review, dispatch |
| `full` (default) | 1–10: everything, repeated | A `$W` folder | The owner says stop | — |

`setup`, `status` and `end` are separate modes (see SKILL.md). They are not stages of the loop.

## Choosing the mode

1. An explicit mode wins. If the user said "full cycle", "everything" or gave no hint but said "continue", it is
   `full`.
2. If the request is vague ("work on the plan"), ask one AskUserQuestion with the five modes, `full` first.
3. If the repo has no `$W` folder, no mode can run. Say so and offer **Setup** first. Setup is a prerequisite, not
   a stage, and it is never run silently.
4. Optional words after the mode: `parallel` or `sequential` (for `orchestrate`/`full`: force or forbid worktrees for the pair,
   overriding `PARALLEL_PAIRS`), a target: a phase (`plan phase 3`), batch ids (`orchestrate B14+B15`,
   `review B14+B15`) or a commit range (`review abc123..HEAD`). Without a target, take the NEXT item from the
   handoff.

## Rules that hold in every mode

- Resume first, as in `session-loop.md` §1: read the handoff, then check `git log`, `git status` and running
  processes against it. Reality wins over the handoff. This is cheap and a single-step run needs it as much as a
  full one.
- The RULE CHECKLIST and the non-negotiables in SKILL.md still apply. A single-step mode drops stages. It does
  not relax any rule of the stages it keeps.
- Do not do another stage "while you are here". If a mode finds the previous stage is incomplete (no brief, no
  report, findings still open), stop and say which mode to run first.
- Finish by recording where the work stands, so a different session can pick up with the next mode: run
  `python3 $ES/scripts/status.py --repo . --plan-id <PLAN_ID> --set-stage <STAGE> --next-mode "<mode + target>"`
  (stages: `PLANNED`, `IMPLEMENTED-UNREVIEWED`, `REVIEWED-UNCOMMITTED`, `FIX-ROUND-NEEDED`, `COMMITTED`), then write one
  ledger line in `progress.md` and the STAGE line of the LIVE STATUS block. `status.py` prints the stage at the top of
  every later session.
- End with one line to the owner: what was done and the exact next mode to run
  (for example: "Both batches implemented, not reviewed. Next: `review B14+B15`.").

## plan

Entry check: `$W` exists, the plan file is readable, and the next phase or batch is known (handoff NEXT, or the
target the owner gave).

1. Resume and status (`session-loop.md` §1–2). Give the owner done/left % and the open OWNER-REVIEW items.
2. If the phase has no survey yet, dispatch the read-only survey (`survey-brief-template.md`) on the helper model.
   Read it, then append ORCHESTRATOR RULINGS and BATCH ORDER (each batch marked MECHANICAL or JUDGEMENT, paired
   where the file sets are disjoint).
3. Rule the DECISIONS that are open (`session-loop.md` §3). Owner-reserved ones go to the owner with a
   recommendation.
4. Write each brief from `brief-template.md` and size-check it against BATCH_MINUTES (`session-loop.md` §4).
5. Re-check every brief against the current code (BASE, file:line facts, rulings) and fix it.

Done when: every batch in the target has a brief marked ready, the pair order is written down, and no
owner-reserved decision blocks it. Show the owner the batch order, the pairs and the brief paths. Stage reached:
`PLANNED`.

## orchestrate

Entry check: each batch to run has a brief that was re-checked in this session, BASE matches `git log -1`, and the
working tree holds nothing unexplained (`git status`). If a brief is stale or missing, stop and name `plan`.

0. **Parallel or sequential?** Run the pair in git worktrees at the same time when the survey tags it `PARALLEL-OK`,
   `PARALLEL_PAIRS` is not `off`, the previous pair is committed and no shared port/database is involved
   (`parallel-pairs.md`, which has the exact steps: add → dispatch both → snapshot → land). In that case this mode ends
   with the pair **landed** in the main tree and the integration gate written to `runs/<B>/integration-gate.log`.
   Otherwise follow steps 1–5.
1. Load the delegate skill of the lane once (`lanes.md`).
2. Dispatch pair A, wait for the notification (never poll), save its report to `runs/<A>/REPORT.md`, check
   completeness (per-ruling list, DECISIONS, every self-check line), and resume the same session for anything
   missing.
3. Dispatch pair B on top of the uncommitted A, with the PAIR block filled. Same report handling.
4. Quota or limit error: use the lane's fallback with the same brief and tell the owner in one line.
5. Rule the DECISIONS in both reports (`session-loop.md` §3).

Done when: both reports are saved, complete and their DECISIONS are ruled (parallel: and the pair is landed and the
integration gate has run). Do not read the reports as a review.
They are evidence for the reviewer. Stage reached: `IMPLEMENTED-UNREVIEWED`. Tell the owner the tree is uncommitted
and not yet reviewed.

## review

Entry check: the pair's reports and `gate.log` exist in `runs/`, and the changes are either uncommitted in the tree
or in a named commit range. The check BASE is the commit before A. If there are no reports, stop and name
`orchestrate`.

1. Fill `review-full-template.md` (or `review-light-template.md` for MECHANICAL batches) and save it as
   `review-<A>+<B>-prompt.md`.
2. Dispatch the fresh reviewer (`REVIEWER_AGENT`, `REVIEWER_MODEL`, background). Read the whole report, spot-check
   two or three findings and own the verdict (`session-loop.md` §6).
3. FIX ROUND NEEDED: the report lists a fix brief. In this mode, stop and hand it over (see below). Running the
   fix is `orchestrate` on the fix brief, then `review` again with a NEW reviewer.
4. `SendUserFile` the full report plus the plain-language summary (`session-loop.md` §7), then
   `touch $W/<A>+<B>-OWNER_REPORT_SENT` (the `commit` mode checks it). Log the review cost.

Done when: the owner has the report file and the summary. Stage reached: `REVIEWED-UNCOMMITTED` when the verdict is
clean, or `FIX-ROUND-NEEDED` with the fix brief path. Review mode never commits, even when the verdict is clean.

Review-only on code the orchestrator did not dispatch (for example a manual change, or a PR): there are no
implementer reports. Fill the template with the commit range, mark "no implementer evidence" in it, and let the
reviewer re-run the gate (the "untrusted evidence" rule in `pairing-and-review.md`).

## commit

Entry check: the reviewer's last report says clean (or every finding is fixed and a fresh review confirmed it), the
owner has the report file (the `<A>+<B>-OWNER_REPORT_SENT` marker exists in `$W`) and nothing is running. If not, stop and
name `review`.

1. Gate freshness (`git-and-gates.md`): the gate passed on the tree being committed and no source file is newer than
   the gate log. Otherwise re-run the gate.
2. Stage explicit paths only and commit. Two commits for disjoint pairs, one for overlapping ones. Verify with
   `git status`.
3. Bookkeeping in the same turn (`session-loop.md` §9): ledger line, LIVE STATUS, plan status line and a
   lessons line when a new defect class was found.

Done when: the commit exists and the books are updated. Remove the pair's worktrees if it ran in parallel
(`worktree.py remove --all`). Stage reached: `COMMITTED`. Never push unless the owner asked.

## full

`session-loop.md` §1–10 as written: plan, dispatch the pair, review, report, gate, commit, bookkeeping, then the
next pair, until the owner says stop. This is the default when nothing narrower was asked. It records the stage
reached after each commit as usual, and it ends with the **End of session** ritual when the owner stops.

# Pairing and review rules

## Batches

- About BATCH_MINUTES each (default 30): estimate files × complexity. If the estimate is more than ~15% over,
  split before dispatch. If it truly cannot be split, ask the owner. The plan was cut into 60–120 min batches
  once, and both quality and the review budget suffered.
- Each batch in the order is marked **MECHANICAL** or **JUDGEMENT**. That decides LIGHT vs FULL review.

## Pairs (the default)

- Adjacent batches with disjoint files run as a pair. A runs first, then B on top of the **uncommitted** A, each
  in its own new implementer session. ONE reviewer cycle covers both, and the check BASE is the commit before A.
- A batch stays single only when the owner must answer something between A and B. Migrations or shared files are
  not a reason to go single.
- B's brief carries the PAIR block: do not edit A's files. If B breaks one of A's tests, B updates that test to
  the new contract and reports it. B never adds a guard elsewhere to keep an old assertion green.
- A's brief must not start a long full gate. B runs the full gate on the combined tree.
- Commits: disjoint file sets → two commits, A first. If the sets overlap, or a fix round edits both → one
  combined commit naming both.

## Reviewer

- **Fresh** strong-model subagent per pair (`REVIEWER_AGENT`, `REVIEWER_MODEL`, effort `REVIEWER_EFFORT`). It runs
  in `acceptEdits` mode with project allow rules so it can fix without prompts. No pre-review by the orchestrator.
- **FULL review** (every JUDGEMENT batch, every fix round of one, every phase close-out):
  - reads EVERY changed or new non-test line (new files whole, edits as diffs), plus migrations, env examples,
    container files and e2e suites; lists the files read;
  - walks every checkpoint of `review-checklist.md`, every group of `performance-checklist.md` and every
    rules-file section, each with evidence;
  - sampling is never allowed.
- **LIGHT review** (MECHANICAL batches only): scope check, the proofs re-run, ≥15 sampled hunks plus every
  non-mechanical hunk, behaviour kept, tests not weakened. If judgement hunks turn up, they are read in full or
  the batch is promoted to FULL.
- Pair: every finding names its batch (A / B / both), and "Brief followed exactly" is judged per batch.

## Evidence first, no blind re-runs

1. The implementer writes gate output to `runs/<id>/gate.log` and live checks to `runs/<id>/live-checks.log`, then
   pastes the summaries **verbatim**. The gate is its last step, so no source file may be newer than gate.log.
2. The reviewer verifies: the pasted summaries match the logs, there is no source file newer than the log, and the
   self-check answers every line.
3. The reviewer re-runs ONLY (a) the gate parts and suites its own edits touch, (b) anything that failed, was
   skipped or rests on an unproven excuse (prove or disprove it, e.g. at BASE), and (c) the live checks of code
   it changed. If it edited nothing and the evidence is clean, it writes "NOT RE-RUN — evidence verified: <paths>".
4. Untrusted-evidence lanes: re-run everything.

## Fix policy

- The reviewer fixes, itself, every minor or medium finding that needs no design decision and touches fewer than
  ~15 files: naming, comments, a missing owner filter or index, a magic value, a missing locale text, a long
  function split by responsibility, dead code.
- Cap: if there are more than ~10 non-trivial findings, it fixes only the small ones and hands the rest back.
- It hands back findings that need a design decision, change behaviour beyond the brief, miss a whole brief item,
  or touch ~15+ files. It writes these as `<id>-fix1-brief.md` in brief format, with DECISIONS NEEDED first.
- Fix round → same implementer lane resumed, then a NEW fresh reviewer given the previous report. A continued
  reviewer (SendMessage, cycle 2+) re-runs only what the fix touched.
- Every issue in a touched file gets fixed before the commit, including old code in that file.

## Report wording

Plain words only. One line per checkpoint by its name ("Run really finished", "Every changed line read",
"Performance — query cost", "<rules file> — one type per file"). Each line is ✅ evidence / ❌ file:line /
⚠ accepted + reason / NOT RUN + why. Then "Fixed by reviewer", "Handed to implementer" and "Fix plan". Write it
so a fresh reviewer could verify every finding is closed.

## Review cost

Log tokens, tool calls and minutes per review in the ledger. Compare after 3–4 pairs, and tune pair size or
review type when one kind of batch is consistently expensive.

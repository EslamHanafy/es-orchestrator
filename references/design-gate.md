# Design gate (before any design, plan or design change is approved)

Why: a plan written by one agent and reviewed by another shares one framing. Reviewers handed a design check whether it is
**consistent** (races, limits, tests), rarely whether the **approach** is right; and each review fix patches a symptom, which makes
the plan look more reviewed while hiding the real problem. Real case (Matory share-PDF, 2026-11): a planner, a reviewer and three
review cycles approved a 3-second poll timer, and a review finding rated "minor" added a hidden-iframe download to cover a design
gap. The owner spotted both in one message once the flow was explained in plain words.

The gate has four parts. Run all four for a new plan, a new phase with a user-facing flow, and any design change. A purely mechanical
phase (renames, package bumps, proven deletions) skips (a)–(c) but keeps (d).

## (a) Prior art

The design document opens with a short researched section:
- how 2–3 known products or published patterns solve the same problem, with sources (web search allowed; cite links);
- at least 2 real alternatives with trade-offs (requests/work per user action, resources held, infrastructure limits such as proxy
  timeouts, client/browser behaviour, complexity);
- the chosen option and every rejected one, each with its reason.

## (b) Unanchored challenger

Before the normal design/plan review, dispatch a fresh strong-model agent with `templates/design-challenger-prompt.md`. It gets
ONLY the problem, the platform facts, the constraints and the owner's goals in their own words. It is never shown the design and
is told which paths not to open (the spec, the plan, the survey/briefs folder, any code already written for the design). It
proposes its own design. The orchestrator compares both and answers every difference in the design document ("adopted",
"rejected because …"). Differences the orchestrator cannot settle with a reason go to the owner with a recommendation.

## (c) Flow walkthrough

For every user-facing action the design states, step by step:
- the requests and the database/queue work the action causes (a "per user action" table: requests, DB work, what the user sees);
- what the user sees at each step;
- every unhappy path (failure, overload, revoked/expired access, data changed underneath, network drop, navigation away, slow device).

The owner approves the design from a **plain-words summary of this walkthrough** (plus a diagram when it helps), not only from the
technical spec. Owners catch approach mistakes in plain words that they cannot see in a spec.

## (d) Cause or symptom

Every change a review (design, plan or code) adds is labelled "fixes the cause" or "works around a symptom because …". A
workaround is never ruled "minor" by the orchestrator: it goes to the owner with the cause-level alternative.

Red flags that force the question "is there a standard way?":
- timers that poll, sleeps, blind retries;
- hidden iframes, simulated clicks, "just in case" locks or flags;
- a component whose only job is to cover another design choice;
- a header, limit or security setting relaxed to make a feature work.

## Where it plugs in

- `plan` mode step 0 (`run-modes.md`), before surveys and briefs of a phase that the gate covers.
- Setup: if the plan file does not exist yet, the gate runs inside its writing (superpowers:writing-plans or the owner's own process)
  before the plan is approved.
- RULE CHECKLIST line in the handoff (templates/ORCHESTRATOR_HANDOFF.md).
- Reviews: the fix policy (`pairing-and-review.md`) and the review templates carry the cause-or-symptom label and the red-flag list.

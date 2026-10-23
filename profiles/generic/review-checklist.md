# MANDATORY REVIEW CHECKLIST — run ALL of it after EVERY implementation run; report EACH checkpoint

No checkpoint is skipped or summarized as "fine" without evidence. If one cannot run, report it as NOT RUN with the reason.
SOURCE OF TRUTH: {{RULES_FILES}}. Re-read it in full before every review; it wins wherever it says more than this list. Then
read the brief, the plan task(s), the contract/spec sections, and the rulings the brief cites.

## Preparation
- **Rules re-read**: the rules file, brief, plan task(s) and contract sections of this batch.
- **Run really finished**: no implementer/relay process for the run; no files newer than `runs/<id>/result.json`.
- **Full change list**: `git status --porcelain -uall` + `git diff --stat <BASE>`, including files the report did NOT mention.

## Checkpoints (each: ✅ evidence / ❌ file:line / ⚠ accepted + reason / NOT RUN + why)
1. **Brief followed exactly**: every ruling done as specified (names, files, shapes); no scope creep; nothing missing; every
   implementer decision or deviation judged (accept/reject + why).
2. **Every changed line read**: EVERY changed/new non-test source line (new files whole, edits as diffs), plus migrations,
   example config, container/CI files and e2e suites. List the files read.
3. **Plan gaps and edge cases**, each checked: empty / null / one item; huge data; two clients or devices at once; replay after
   a lost response; clock skew; deleted parent; expired or revoked session; every language and direction; currencies or units
   with unusual precision; boundaries (limits, page sizes, dates). Gaps become a ruling or a dated ADDED line in the plan.
4. **Behaviour kept and data safety**: shipped behaviour preserved (compare with BASE); no invented behaviour; no data-loss
   path; transactional integrity; side effects after commit never fail or duplicate a committed write.
5. **Performance**: walk EVERY group of performance-checklist.md for every changed file, ✅/❌ per group with file:line.
6. **Contract fidelity**, field by field: names, casing, types, nullability, enum values, status/error codes, envelopes,
   pagination, idempotent replays.
7. **Security and privacy**: authorization on every entry point; owner/tenant filter on every scoped query (including bulk
   statements); input validated; no injection-prone string building; no secrets or personal data in logs, errors or responses;
   rate limits where the plan asks.
8. **SOLID / DRY / reuse**: single responsibility (no god classes/handlers/widgets); architecture direction respected; existing
   helpers searched and reused; the second copy of any logic extracted; no pass-through wrappers.
9. **Files and naming**: one public type per file; enums in their own files; file name = type name; folder conventions.
10. **Comments**: what the rules file requires (on every type/member where required; inline for complex logic; no narration).
11. **Hidden defaults and wiring**: no silent fallbacks or optional dependencies; settings validated at startup; dependency
    lifetimes correct; components wired explicitly.
12. **Errors**: the project's error type only; typed catches; no catch-alls, empty catches or swallowed failures; failures carry
    a usable code + message; framework/SDK exceptions mapped at the boundary.
13. **Constants and configuration**: no magic strings/numbers; env/config over hard-coded values; example config updated.
14. **Localization**: every user-visible text in all locale files ({{LANGUAGES}}); technical ids not localized; direction
    handled for RTL languages.
15. **Dead code**: removed APIs have no callers (search proofs); new code has callers; no unused imports, parameters, settings,
    keys, routes or enum values.
16. **Tests**: the brief's named tests exist and assert what their names say; no weakened or deleted invariants
    (`git diff --stat <BASE> -- {{TEST_DIRS}}`); tests that need real infrastructure actually ran.
17. **Gates**: the implementer's gate evidence verified against its log; re-run only what the evidence rules allow, otherwise
    "NOT RE-RUN — evidence verified: <where>".
18. **Format-only churn**: any file whose diff is only formatting and was not required → restored from BASE.
19. **Function length**: max {{FN_MAX_LINES}} lines per function, judged by SOLID, not count alone. Every over-limit function in a
    changed file is listed; shorter functions that do more than one job or mix abstraction levels are flagged; fragments split
    only to beat the count are rejected. Over-limit or multi-job functions block, including OLD code in touched files.
20. **Live evidence**: {{LIVE_CHECK}}. Each new or changed interface is exercised, and its request/response (or screen state) is
    compared with the contract or design.
21. **Bookkeeping** (orchestrator): progress ledger line, handoff LIVE STATUS, plan ADDED lines, roadmap row at the close-out.
22. **Rules-file section walk**: one line per section/rule of {{RULES_FILES}}, by its own words.

{{PROFILE_CHECKPOINTS}}

## Report format to {{OWNER_NAME}} (plain language)
One line per Preparation item and checkpoint above (performance = one line per group; rules walk = one line per rule), each
✅/❌/⚠/NOT RUN with the concrete evidence. Then "Fixed by reviewer", "Handed to implementer" and "Fix plan".

# Review lessons — implementer self-check (embedded in EVERY brief; answer each line in REPORT.md)

Before you write REPORT.md, run `{{PLAN_DIR}}/check.sh <BASE> …` until it prints `ALL GATES PASS`. Then go through every line
below against YOUR diff and write `✅` or `fixed: <what>` per line in a "Self-check" section of REPORT.md. The orchestrator
appends every new defect class a review finds, so this list grows; that growth is the point.

## Contract and behaviour
1. Shapes exactly as the contract/brief: names, casing, types, nullability, enum values, status/error codes.
2. Never remove shipped functionality the brief does not remove; untouched flows behave identically.
3. No invented behaviour, contracts or payloads that the brief or contract does not define.

## Values and defaults
4. No invented fallbacks (`?? ''`, `?? 0`, `|| 'guest'`, fake placeholders). If a value can be missing, the type says so and
   there is a real state for it.
5. No optional dependencies or parameters with silent defaults; required settings are validated at startup.
6. No magic strings or numbers: constants, the error-code catalogue, or settings from env/config.

## Structure ({{RULES_FILES}})
7. Functions ≤ {{FN_MAX_LINES}} lines AND one job each (load vs map vs rule vs persist vs layout). Split by responsibility, not
   into fragments. Long functions in OLD code of files you touch are also fixed.
8. One public type per file; enums in their own files; file name = type name.
9. DRY / reuse first: search the codebase for an existing helper before writing one; the second copy of logic gets extracted.
10. Comments as the rules file requires (on every type/member where required; inline for complex logic; no narration).
11. Layering/architecture direction respected; no pass-through wrappers; no god classes.

## Errors
12. No catch-alls and no empty catch blocks. Catch typed failures, map each kind, and never swallow: a caught failure becomes
    state or a reported error.
13. Never log or return secrets or personal data (tokens, URLs with signatures, e-mails, identifiers).

## Localization
14. Every user-visible text exists in ALL locale files ({{LOCALE_FILES}}) with real translations ({{LANGUAGES}}); unused keys
    are deleted.

## Scope and hygiene
15. Only the files the brief needs; no format-only churn in files you did not otherwise change; format explicit files only.
16. No dead code after your change: unused imports, parameters, settings, keys, endpoints, enum values.
17. Never run git commands that change files or the index; no background helpers, subagents or servers except what the gate
    starts; no TODO/FIXME.
18. Never delete or reset data yourself (databases, volumes, files outside your diff). Stop and report it under DECISIONS NEEDED.

## Evidence and tests
19. Gate and live-check output is pasted VERBATIM from the log files you produced in THIS run (cite the path); never retyped,
    summarized or invented.
20. Sample responses are captured by the tool (e.g. `curl … | jq`) and pasted verbatim, never rebuilt from memory.
21. Tests named in the brief exist, pass and assert what their names say; no existing test is weakened or deleted unless it only
    tested deleted code.
22. A test named for a property (order, merge, uniqueness, rollback) uses input that could violate that property.
23. Visibility assertions compare counts before and after, never `any`/`contains` on a shared store.
24. Search the test tree for an existing helper before adding a private one.
25. Components are wired explicitly in the composition root, never "if the container happens to find them".
26. Prove every suite you changed actually ran: paste its own check count. A suite that silently skipped is not green.

{{PROFILE_SELF_CHECK}}

## Project lessons (appended by the orchestrator after reviews; newest last)

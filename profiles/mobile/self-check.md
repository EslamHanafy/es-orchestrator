## Mobile (profile)
M1. No `!` (or force-unwrap) to silence the analyzer. Restructure instead (pattern match, early return, required field).
M2. No pre-selected choices in sheets or pickers unless the design shows one selected.
M3. No hard-coded units, separators, joins or date patterns inline. Use the existing formatter/helper/constant (one formatter
    per concept).
M4. Switches on an enum that answer "what is X for this value" live on the enum as an exhaustive getter, with no default branch.
M5. Member order per the rules file. Every model field is in copyWith (clearable when nullable), equality and every serializer.
M6. Every async path that can throw sets the failure state the UI reads, including submit paths. A second tap while busy is a
    no-op. A stale result after a context change (selected item, account) is dropped.
M7. The approved design 1:1: text, order, tone, icons, spacing roles and button kinds. Nothing added, nothing missing.
    Preview-only parts are never copied.
M8. Shared components only (sheets, dialogs, rows, banners, buttons). No hand-made equivalents and no raw platform sheet/route
    calls in widgets.
M9. Sheets/dialogs close with their OWN context. Routes are pushed through the app router.
M10. No direct `now()` in presentation. The clock comes from the state holder or an injected clock.
M11. No dead taps: every visible action does something, or it is hidden/disabled per the design.
M12. Rows and buttons that depend on live state (offline, busy) rebuild from that state, not from a one-time read.
M13. Bidi: numbers, hosts and times are LTR-isolated; user text is first-strong-isolated.
M14. Locale key classes regenerated. A string that is already translated is never translated again.
M15. No tests the brief did not ask for. Data-layer batches add a real local-DB test using the project's harness.

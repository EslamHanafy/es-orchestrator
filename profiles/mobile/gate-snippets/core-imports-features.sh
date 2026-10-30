# Gate snippet: shared/core code never imports feature code (checked on changed core files).
# Override CORE_RE / FEATURE_IMPORT_RE in the copied gates.d file for another layout. In the import regex, `.` stands for the
# quote character (grep -E has no portable escape for it), so it matches both import '...' and import "...".
[[ -n "${CORE_RE:-}" ]] || CORE_RE='^lib/core/'
[[ -n "${FEATURE_IMPORT_RE:-}" ]] || FEATURE_IMPORT_RE='import .(package:[a-z_]+/)?(\.\./)*features/'
core_bad="$(grep -E "$CORE_RE" "$OUT/src" | while read -r f; do grep -HnE "$FEATURE_IMPORT_RE" "$f"; done)"
if [[ -n "$core_bad" ]]; then fail "core imports features:"; echo "$core_bad" | head -20; else pass "core never imports features"; fi

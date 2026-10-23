# Gate snippet: design-preview code never leaks into production code.
PREVIEW_RE="${PREVIEW_RE:-theme/preview/}"; PREVIEW_ALLOWED_RE="${PREVIEW_ALLOWED_RE:-(app_router|/preview/)}"
prev_bad="$(grep -vE "$PREVIEW_ALLOWED_RE" "$OUT/src" | while read -r f; do grep -HnE "import .*$PREVIEW_RE|LocaleKeys\.preview" "$f"; done)"
if [[ -n "$prev_bad" ]]; then fail "preview code used in production:"; echo "$prev_bad" | head -20; else pass "preview isolation"; fi

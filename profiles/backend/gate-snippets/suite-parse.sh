# Gate snippet: every shell e2e suite parses, so a syntax error cannot make a suite skip silently.
SUITE_GLOB="${SUITE_GLOB:-tests/suites/*.sh}"
parse_bad=""
for s in $SUITE_GLOB; do [[ -f "$s" ]] && ! bash -n "$s" 2>/dev/null && parse_bad+="$s "; done
if [[ -n "$parse_bad" ]]; then fail "suites do not parse: $parse_bad"; else pass "e2e suites parse"; fi

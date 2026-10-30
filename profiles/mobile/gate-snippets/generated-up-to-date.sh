# Gate snippet: generated code (locale keys, codegen) is up to date. OPT-IN: set GEN_CMD and GEN_FILES for the project,
# for example in the copied gates.d/generated-up-to-date.sh:
#   GEN_CMD="dart run build_runner build --delete-conflicting-outputs"; GEN_FILES="lib/generated/app_localizations.dart"
# NOTE: this gate REGENERATES the files in the tree being gated. A stale file is reported once and fixed in place; review
# and include the regenerated files, then re-run the gate (the freshness rule applies to them like any source).
GEN_CMD="${GEN_CMD:-}"; GEN_FILES="${GEN_FILES:-}"
if [[ -z "$GEN_CMD" || -z "$GEN_FILES" ]]; then
  skip "generated files (set GEN_CMD and GEN_FILES in gates.d/generated-up-to-date.sh)"
else
  gen_before="$(cat $GEN_FILES 2>/dev/null | shasum)"
  timed bash -c "$GEN_CMD" > "$OUT/gen.txt" 2>&1
  gen_after="$(cat $GEN_FILES 2>/dev/null | shasum)"
  if [[ "$gen_before" != "$gen_after" ]]; then fail "generated files were stale (now regenerated; review and include them): $GEN_FILES"
  else pass "generated files up to date"; fi
fi

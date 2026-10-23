# Gate snippet: generated code (locale keys, codegen) is up to date. Edit GEN_CMD and GEN_FILES for the project.
GEN_CMD="${GEN_CMD:-dart run easy_localization:generate --source-dir assets/languages -f keys -o locale_keys.g.dart}"
GEN_FILES="${GEN_FILES:-lib/generated/locale_keys.g.dart}"
gen_before="$(cat $GEN_FILES 2>/dev/null | shasum)"
bash -c "$GEN_CMD" > "$OUT/gen.txt" 2>&1
gen_after="$(cat $GEN_FILES 2>/dev/null | shasum)"
if [[ "$gen_before" != "$gen_after" ]]; then fail "generated files were stale (now regenerated — review and include them): $GEN_FILES"
else pass "generated files up to date"; fi

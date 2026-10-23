# Gate snippet: architecture direction in changed source files (inner layers never import outer ones).
# Edit LAYER_RULES: "<path regex of an inner layer>|<import regex it must not contain>".
LAYER_RULES=(
  '/Domain/|(using [A-Za-z.]*\.|import .*[/.])(Application|Infrastructure|Api)[./;"'"'"']'
  '/Application/|(using [A-Za-z.]*\.|import .*[/.])(Infrastructure|Api)[./;"'"'"']'
)
layer_bad=""
for rule in "${LAYER_RULES[@]}"; do
  path_re="${rule%%|*}"; import_re="${rule#*|}"
  while read -r f; do
    [[ "$f" =~ $path_re ]] || continue
    hits="$(grep -nE "$import_re" "$f" || true)"
    [[ -n "$hits" ]] && layer_bad+="$f: ${hits%%$'\n'*}"$'\n'
  done < "$OUT/src"
done
if [[ -n "$layer_bad" ]]; then fail "layering:"; printf '%s' "$layer_bad"; else pass "layering"; fi

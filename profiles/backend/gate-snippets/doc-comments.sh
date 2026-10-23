# Gate snippet: a doc comment on every ADDED declaration (types, methods incl. private, constructors, properties).
# Edit DOC_PREFIX (e.g. '///' for C#/Dart/Rust, '\*' for JSDoc/KDoc/Javadoc block lines) and DECL_RE for the language.
DOC_PREFIX='///'
DECL_RE='^[[:space:]]*((public|private|protected|internal|static|async|override|virtual|sealed|abstract|readonly|partial)[[:space:]]+)+[A-Za-z<>\[\],?. ]+[[:space:]]+[A-Za-z_][A-Za-z0-9_]*[[:space:]]*(\(|\{|=>|$)'
doc_bad=""
while read -r f; do
  git ls-files --error-unmatch "$f" >/dev/null 2>&1 && added="$(git diff -U0 "$BASE" -- "$f" | grep -E '^\+[^+]' | sed 's/^+//')" || added="$(cat "$f")"
  while IFS= read -r line; do
    [[ "$line" =~ $DECL_RE ]] || continue
    prev="$(grep -nF -- "$line" "$f" | head -1 | cut -d: -f1)"; [[ -z "$prev" || "$prev" -lt 2 ]] && continue
    above="$(sed -n "$((prev-1))p" "$f")"
    [[ "$above" =~ ^[[:space:]]*(\[|@) ]] && above="$(sed -n "$((prev-2))p" "$f")"   # skip one attribute/annotation line
    [[ "$above" == *"$DOC_PREFIX"* || "$above" == *'*/'* ]] || doc_bad+="$f:$prev: ${line#"${line%%[![:space:]]*}"}"$'\n'
  done <<< "$added"
done < "$OUT/src"
if [[ -n "$doc_bad" ]]; then fail "doc comments missing:"; printf '%s' "$doc_bad" | head -30; else pass "doc comments on added declarations"; fi

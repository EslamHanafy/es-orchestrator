# Mobile gate hooks (fill check.sh settings)

| Stack | BUILD_CMD | LINT_CMD | FORMAT_CHECK (files) | TEST_CMD | TEST_FAILURES_EXTRACT |
| --- | --- | --- | --- | --- | --- |
| Flutter | `none` (analyze covers it) | `flutter analyze` | `dart format --output=none --set-exit-if-changed` | `flutter test test/` | `grep -E '\[E\]$' \| sed -E 's/^.*(test\/[^:]*):.*/\1/'` |
| React Native | `npx tsc --noEmit` | `npx eslint .` | `npx prettier --check` | `npx jest --ci` | `grep -E '^ FAIL ' \| awk '{print $2}'` |
| Android (Kotlin) | `./gradlew assembleDebug` | `./gradlew lint detekt` | `./gradlew ktlintCheck` (tree) | `./gradlew testDebugUnitTest` | parse `build/test-results/**/*.xml` |
| iOS (Swift) | `xcodebuild build -scheme <s> -destination 'generic/platform=iOS Simulator'` | `swiftlint` | `swiftformat --lint` | `xcodebuild test …` | `grep -E "error: -\[" ` |

Extra gates worth adding:
- **Generated code up to date** (`generated-up-to-date` snippet, opt-in: set `GEN_CMD` and `GEN_FILES` in the copied
  `gates.d/generated-up-to-date.sh`; it regenerates in place and reports a stale file once).
- **Preview isolation**: no import of the design-preview folder outside the router's preview entry; no preview keys in
  production code.
- **`core` never imports `features`**: grep the new imports of changed core files.
- **Locale parity**: `LOCALE_FILES` covers `.json`, `.arb`, `.properties` and `.strings`, including placeholder parity. For other
  formats (`strings.xml`, YAML, `.po`) the gate reports "unsupported"; write a small parser hook.
- **Format churn**: run the formatter on BASE copies of changed files to spot format-only diffs (restore those from BASE).

Device checks cannot run in CI-like gates. The reviewer reports them as NOT RUN unless the owner or a simulator run
produced evidence (screenshots in `runs/<id>/`). Better function-length scanners: `dart_code_linter`
(`source-lines-of-code`), eslint `max-lines-per-function`, detekt `LongMethod`, swiftlint `function_body_length`.

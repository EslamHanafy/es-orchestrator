# Web gate hooks (fill check.sh settings)

| Stack | BUILD_CMD | LINT_CMD | FORMAT_CHECK (files) | TEST_CMD | TEST_FAILURES_EXTRACT |
| --- | --- | --- | --- | --- | --- |
| Angular | `npx ng build --configuration production` | `npx ng lint` | `npx prettier --check` | `npx ng test --watch=false` | `grep -E 'FAILED$' \| sed -E 's/ FAILED$//'` |
| React/Vite | `npm run build` | `npx eslint .` | `npx prettier --check` | `npx vitest run` | `grep -E '^ FAIL ' \| awk '{print $2}'` |
| Next.js | `npx next build` | `npx next lint` | `npx prettier --check` | `npx jest --ci` | `grep -E '^ FAIL ' \| awk '{print $2}'` |
| Vue | `npm run build` | `npx eslint .` | `npx prettier --check` | `npx vitest run` | `grep -E '^ FAIL ' \| awk '{print $2}'` |

Extra gates worth adding (gates.d snippets): bundle budget (`size-limit`, or Angular `budgets` in angular.json),
accessibility (`eslint-plugin-jsx-a11y` / `@angular-eslint/template/accessibility`, or axe in Playwright), and
E2E_CMD = `npx playwright test $E2E`. eslint `max-lines-per-function` is a better length scanner than fnlen.py.

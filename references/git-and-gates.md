# Git safety, staging and gate freshness

## Forbidden in shared trees

Other sessions, implementers and reviewers share the checkout, so never run `git stash`, `checkout`, `restore`,
`reset`, `switch`, `clean`, or `worktree add/remove` (unless the owner set up tracks), and never push unless the
owner asks. To undo a format-only file, use `git show <BASE>:<path> > <path>`. Implementers and reviewers never
run git commands that change files or the index; only the orchestrator stages and commits.

Formatters run on explicit **files** only, never on a directory. Generated migrations, lockfiles produced by
tools, and the database are never hand-edited. Migrations come only from the framework's generator.

## Safe staging

zsh does not word-split `$VAR`, so `git add $FILES` silently adds one bogus path. Use NUL-separated lists:

```bash
git status --porcelain -uall -- <STAGE_PATHS> | awk '{print $2}' | tr '\n' '\0' | xargs -0 git add -A --
```

- A path that a merge deleted aborts an xargs batch. Re-stage those with a `while read -r f; do git add -A -- "$f"; done` loop.
- Stage env/config examples **by name**. Never stage real config, secrets, `.bak-*` backups or `.superpowers/`.
- After staging: `git diff --cached --stat`. Every path must belong to the batch(es) being committed.
- Message: `<type>(<scope>): <batch ids> — <one-line scope>`, ending with the session's attribution line.

## Gate freshness rule (before every commit)

1. The gate log being relied on ran on **this** tree: B's final full gate for a pair, or the orchestrator's own run.
2. `find <SOURCE_DIRS> -newer runs/<id>/gate.log -type f` is **empty**. If anything is newer (a reviewer fix, your
   follow-up), re-run the gate.
3. If the implementer's final gate failed and the reviewer re-ran only a subset, run the full gate yourself.
4. The gate ends with `ALL GATES PASS`. Known failures are listed in `known-test-failures.txt` and nothing else
   fails.
5. Long gates run detached (`nohup … & echo $! > runs/<id>/gate.pid`). Wait on the pid, do not poll the log.

## Merge gate (worktree tracks)

Run a unit gate on the merged tree before each merge commit. Every 2–4 merges, run the FULL gate (including
e2e) on the integration branch HEAD, and keep that counter in LIVE STATUS.

## Allow-lists

`fnlen-allow.txt` (path:function) and `forbidden-allow.txt` (path|rule) hold **ruled** exceptions only. Each line
cites the ruling. Only the orchestrator or a reviewer edits them; an implementer never does.

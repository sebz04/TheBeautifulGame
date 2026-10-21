# MatchMind: agent instructions

- **Start of every session:** read `wiki/README.md`, then only the wiki pages relevant to the task. Don't re-read the whole codebase or plan to orient yourself.
- **Follow** `CONSTITUTION.md`. Track work in `TASKS.md`; the plan is `docs/superpowers/plans/2026-10-21-matchmind.md` (read only the section for the current task).
- **Every commit that changes code** also updates the affected `wiki/` pages and adds a line to `wiki/changelog.md` (TASK-0). Commit messages start with `TASK-N.M:`.
- Dependencies: only those on the Adopt list in `docs/research/open-source-review.md`. Never use real match data.
- Public repo: never commit secrets. They go in `.env` (git-ignored).

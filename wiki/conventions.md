# Conventions

## Workflow per sub-task
1. Move the sub-task to **In Progress** in `TASKS.md`.
2. TDD: write the failing test, run it, implement, run it again.
3. Update the wiki: the touched pages, the module map in `README.md`, and one line in `changelog.md`.
4. Commit `TASK-N.M: <summary>` (code + tests + wiki together). Record the hash on the `Commit:` line and move the sub-task to **Done**.

## Wiki rules (TASK-0)
- Describe what exists, not what is planned. Point to the plan for future work.
- At most 150 lines per page. Use file paths and signatures, not pasted code.
- Edit only the sections that changed. Keep the `Status` line of each page accurate.

## Setup once per clone
`git config core.hooksPath .githooks` enables the pre-commit hook (`.githooks/pre-commit` → `scripts/check_wiki.py`).

## Commands
| Purpose | Command |
|---|---|
| Install | `uv sync` |
| Test | `uv run pytest` (skips `slow`); `uv run pytest -m slow` for season budget and effect tests (nightly in CI) |
| Lint / format | `uv run ruff check .` · `uv run ruff format .` |
| Types | `uv run mypy src` (strict) |
| License gate | `uv run python scripts/check_licenses.py` |
| Wiki check | `uv run python scripts/check_wiki.py` (staged) · `--range main..HEAD` (per commit) |

CI (`.github/workflows/ci.yml`) runs lint, format check, types, tests, the license gate and the per-commit wiki check on every push and PR. The `web` job is a placeholder until TASK-23.

## Testing
- No live model calls in tests (`FakeChatClient`, recorded fixtures in `tests/fixtures/llm/`).
- Tests mirror `src/matchmind/` under `tests/`; tests for `scripts/` live in `tests/scripts/` (`scripts/` is on the pytest path).
- New runtime dependencies must pass the license gate and be added to `THIRD_PARTY_NOTICES.md`.

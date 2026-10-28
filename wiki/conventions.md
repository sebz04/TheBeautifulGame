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
| Run everything locally | `docker compose up` → http://localhost:5173 (first run seeds all 8 matches with template insights into the `matchmind-data` volume; `docker compose down -v` resets) |
| Test | `uv run pytest` (skips `slow`, about 6 min locally); `uv run pytest -m slow` for multi-match statistics, season history, storylines, and effects (nightly in CI) |
| Build the showcase matches | `uv run matchmind build --all --season` (season history once, then the 8 storylines into `MATCHMIND_DB_URL` and the tracking store) · `--scenario scenarios/<id>.toml` for one |
| Lint / format | `uv run ruff check .` · `uv run ruff format .` |
| Types | `uv run mypy src` (strict) |
| License gate | `uv run python scripts/check_licenses.py` |
| Wiki check | `uv run python scripts/check_wiki.py` (staged) · `--range main..HEAD` (per commit) |
| Web (in `web/`) | `npm test` (Vitest) · `npm run lint` (types) · `npm run build` · `npm run dev` (needs the API on :8000) |
| Browser tests | `uv run python scripts/seed_demo.py --db sqlite:///$PWD/data/e2e/e2e.db --data-dir data/e2e`, then in `web/`: `npx playwright test` (starts its own API on :8100 and `vite preview` on :4173) |

CI (`.github/workflows/ci.yml`) runs lint, format check, types, tests, the license gate and the per-commit wiki check on every push and PR. The `web` job runs the frontend's types, Vitest, the build, then seeds a model-free match and runs Playwright (smoke flow, axe at 1280 and 375 px, keyboard).

## Testing
- No live model calls in tests (`FakeChatClient`, recorded fixtures in `tests/fixtures/llm/`).
- Tests mirror `src/matchmind/` under `tests/`; tests for `scripts/` live in `tests/scripts/` (`scripts/` is on the pytest path).
- New runtime dependencies must pass the license gate and be added to `THIRD_PARTY_NOTICES.md`.
- **Slow vs fast tests:** a test that simulates many matches (statistics over seeds, season rounds, storylines, attribute effects) is marked `@pytest.mark.slow` and runs nightly. Single-match checks (determinism, consistency, offsides, red cards, motion) stay in CI. Statistical margins allow for platform differences: the same seed is not bit-identical on macOS and Linux. **Nightly status (2026-10-27):** four attribute-effect thresholds set for the level-2 engine are `xfail` until they're recalibrated for level 3 (TASK-25.5); the job timeout is 5 h and it logs the 15 slowest tests.


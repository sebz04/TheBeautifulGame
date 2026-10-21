# Third-Party Notices

MatchMind uses the open-source software below. Each package keeps its own license; only packages
on the Adopt list in `docs/research/open-source-review.md` may be added. Runtime licenses are
checked in CI by `scripts/check_licenses.py`.

## Runtime dependencies
| Package | License | Use |
|---|---|---|
| pydantic, pydantic-core | MIT | Data models and validation |
| pydantic-settings | MIT | Configuration from environment |
| python-dotenv | BSD-3-Clause | `.env` loading (via pydantic-settings) |
| annotated-types, typing-inspection | MIT | pydantic support |
| typing-extensions | PSF-2.0 | Typing backports |

## Development-only tools (not shipped)
pytest (MIT), pytest-asyncio (Apache-2.0), hypothesis (MPL-2.0), ruff (MIT), mypy (MIT), pip-licenses (MIT).

## Vendored or adapted code
_None yet._ Vendored code keeps its original license header and is listed here.

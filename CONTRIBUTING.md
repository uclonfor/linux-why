# Contributing

Use Python 3.12+. Install `pip install -e '.[dev]'`, then run `ruff check .`,
`ruff format --check .`, `mypy`, `pytest`, and `python -m build` before submitting.

Keep collectors read-only, local, and bounded. All subprocess calls must use Runner
with argument arrays. New observations need sources; heuristics must be marked
inferred and must never stand in for unavailable facts. Add deterministic fixtures
for parsing, failure and permission behavior. Avoid machine-specific expected PIDs.

Never include private command lines, hostnames or system dumps in fixtures. Prefer
small synthetic fixtures with the same format. For Arch releases, also run read-only
smoke tests on a real Arch system (including pacman with and without expac).

No automated publication is configured.

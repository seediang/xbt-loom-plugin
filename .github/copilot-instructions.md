# Copilot instructions

Use uv for Python package management and execution.

- Install dependencies with `uv sync` or `uv add <package>`.
- Run Python with `uv run python` (or `uv run python -m <module>`).
- Run tests with `uv run pytest`.
- Avoid calling `pip` directly unless explicitly requested.
## Code Quality Checks

- Run linting with `uv run ruff check .` to check code style and errors.
- Run formatting check with `uv run ruff format --check .` to verify code formatting.
- Run type checking with `uv run ty check .` for static type analysis.
- Auto-fix issues with `uv run ruff check --fix .` and `uv run ruff format .`.
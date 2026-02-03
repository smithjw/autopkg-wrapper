# autopkg-wrapper Agent Notes

## Overview

This repository provides `autopkg_wrapper`, a CLI for running AutoPkg recipes in CI/CD
with optional trust verification, batching/ordering, reporting, and notifications.

## Environment

- Python is managed by `mise` (see `mise.toml`).
- Dependencies are managed by `uv`.
- Tests are run with `pytest`.
- Packaging uses `hatchling` via `uv build`.
- CLI entry point: `autopkg_wrapper/autopkg_wrapper.py`.

## Build / Lint / Test Commands

Setup:

```bash
mise run install
```

Run tests:

```bash
mise run test
```

Run a single test file:

```bash
uv run pytest tests/test_order_recipe_list.py -v
```

Run a single test by name:

```bash
uv run pytest -k "test_orders_by_type_then_alpha" -v
```

Lint / format with Ruff:

```bash
uv run ruff check .
uv run ruff format .
```

Build package:

```bash
mise run build
```

Regenerate CLI docs:

```bash
mise run docs-cli
```

## Code Style Guidelines

Formatting:

- Follow Ruff formatting defaults with project settings in `.ruff.toml`.
- Line length target is 88; `E501` is ignored but keep lines readable.
- Use double quotes; spaces for indentation; LF line endings.

Imports:

- Ruff enforces import sorting; keep stdlib, third-party, local separated.
- Prefer explicit imports over wildcard imports.
- Use local imports only when needed to avoid optional dependency issues.

Types and typing:

- Target Python 3.14 (`py314`).
- Use type hints for new functions, especially in utils and models.
- Prefer `list[str]`, `dict[str, T]`, and `Path` over legacy typing aliases.
- Use `Protocol` only when you need structural typing (see `recipe_batching.py`).

Naming:

- Modules and functions: `snake_case`.
- Classes: `PascalCase`.
- Constants: `UPPER_SNAKE_CASE`.
- Prefer descriptive variable names for recipes, batches, and paths.

Error handling:

- Use explicit exceptions when failing fast (see `parse_recipe_list`).
- Log errors with context; avoid swallowing exceptions unless necessary.
- When catching broad exceptions, add a comment or log explaining why.

Logging:

- Use `logging` from the stdlib.
- Keep log messages concise and user-actionable.
- Prefer structured or consistent message patterns for batch operations.

I/O and subprocess:

- Use `Path` for filesystem paths; avoid string path math.
- When calling subprocesses, capture output and log debug info.
- Keep command construction explicit for readability and auditability.

Recipes and ordering:

- Keep recipe identifiers as full filenames (e.g. `Foo.upload.jamf`).
- Ordering logic lives in `autopkg_wrapper/utils/recipe_ordering.py`.
- Batching logic lives in `autopkg_wrapper/utils/recipe_batching.py`.

Tests:

- Place tests in `tests/` with `test_*.py` naming.
- Use `pytest` fixtures or `SimpleNamespace` for lightweight args.
- Mock subprocess calls rather than invoking external tools.

Docs:

- User-facing behavior changes should be reflected in `README.md`.

## Repository Notes

- No Cursor rules or Copilot instructions were found in this repo.
- If new rules are added under `.cursor/rules/`, `.cursorrules`,
  or `.github/copilot-instructions.md`, include them here.

## Key Paths

- CLI: `autopkg_wrapper/autopkg_wrapper.py`
- Recipe model: `autopkg_wrapper/models/recipe.py`
- Utils: `autopkg_wrapper/utils/`
- Tests: `tests/`

# autopkg-wrapper Agent Notes

## Overview

This repository provides `autopkg_wrapper`, a CLI for running AutoPkg recipes in CI/CD contexts with optional trust verification, batching/ordering, reporting, and notifications.

## Tooling

- Python: managed by `mise` (see `mise.toml`)
- Dependency management: `uv`
- Tests: `pytest`
- Packaging: `hatchling` via `uv build`

## Common Commands

```bash
mise run install
mise run test
mise run build
```

## Key Libraries

- `requests` for Slack notifications
- `PyGithub` for GitHub automation
- `ruamel.yaml` for recipe list parsing
- `jamf-pro-sdk` for Jamf integrations in report processing

## Project Layout

- `autopkg_wrapper/autopkg_wrapper.py` CLI entry point
- `autopkg_wrapper/models/recipe.py` Recipe model and execution
- `autopkg_wrapper/utils/` batching, ordering, logging, reporting helpers
- `autopkg_wrapper/notifier/` Slack notifier
- `tests/` pytest suite

## Development Notes

- Use full recipe identifiers (`Foo.upload.jamf`) in logs/notifications to avoid ambiguity.
- Recipe processing order and batching are controlled by `--recipe-processing-order`.
- Keep documentation updates in `README.md` when user-facing behavior changes.

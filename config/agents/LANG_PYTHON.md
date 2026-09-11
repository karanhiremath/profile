# Python conventions

- **Always `uv` + virtual environments.** Never bare `pip install`.
  - `uv venv` / `uv pip install` / `uv run` / `uv sync`.
- Target a pinned interpreter; commit `uv.lock` / `requirements.lock` for apps.
- Lint+format with `ruff`; type-check with `mypy` or `pyright` where configured.
- Prefer `pathlib`, `argparse`/`typer` for CLIs, `logging` over `print` in libraries.
- Tools: importable module + thin CLI entrypoint; `--auto-approve` gate for destructive actions.
- Tests with `pytest`; run before claiming done.

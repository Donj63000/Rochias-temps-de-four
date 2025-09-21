# Repository Guidelines

## Project Structure & Module Organization
- Application entry points: `Main.py` (compat shim) and `python -m rochias_four`.
- Core modules live under `rochias_four/` (`app.py`, `calibration.py`, `config.py`, `theme.py`, `utils.py`, `widgets.py`).
- Assets are stored beside their module (e.g., `rochias_four/rochias.png`).
- IDE metadata in `.idea/`; virtual environment under `.venv/` (keep out of commits).

## Build, Test, and Development Commands
- `python Main.py` — launch the Tkinter dashboard using the legacy script path.
- `python -m rochias_four` — preferred entry point invoking `rochias_four.__main__`.
- `python -m py_compile Main.py rochias_four\*.py` — quick syntax validation for all modules.

## Coding Style & Naming Conventions
- Language: Python 3.11+ expected; follow PEP 8 (4-space indentation, snake_case functions, PascalCase classes).
- UI strings stay in French; keep diacritics consistent.
- Centralise colours/constants in `theme.py` or `config.py`; avoid hard-coding duplicates.
- Prefer small, focused helpers in `utils.py`; share widgets via `widgets.py`.

## Testing Guidelines
- No automated test suite yet; validate with `python -m py_compile ...` and manual UI runs.
- For new logic, add lightweight regression scripts under `scripts/` (create if needed) and remove temporary tooling before merging.
- When touching calibration math, double-check outputs against `EXPS` reference data.

## Commit & Pull Request Guidelines
- Commits should be imperative and scoped (e.g., `Refactor calibration helpers`, `Fix widget palette import`).
- Reference related issues in the body (e.g., `Refs #42`) and note manual test evidence.
- Pull requests include: summary of changes, testing notes (`python -m rochias_four`, screenshots for UI changes), and checklist confirmation that prefs files/virtual envs remain untracked.

## Security & Configuration Tips
- Do not commit personal calibration datasets; store environment-specific files outside the repo.
- Preferences file (`~/.four3_prefs.json`) is generated at runtime — verify it is ignored.
- When distributing binaries, bundle the `rochias_four` package directory with `rochias.png` intact.

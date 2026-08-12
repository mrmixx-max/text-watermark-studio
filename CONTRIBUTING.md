# Contributing ## Development setup ```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pytest -q
``` ## Workflow 1. Create a branch.
2. Add or update tests.
3. Run `pytest -q`.
4. Open a pull request with a clear summary. ## Style - Keep the stdlib-first approach where practical.
- Prefer small, testable modules.
- Document capability limits honestly.
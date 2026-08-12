python -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -e .[dev]
pytest -q
python -m build

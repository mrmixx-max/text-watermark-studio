PYTHON ?= python
VENV ?= .venv
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
UVICORN := $(VENV)/bin/uvicorn

.PHONY: venv install dev test run api build clean

venv:
	$(PYTHON) -m venv $(VENV)

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -e .

dev: venv
	$(PIP) install --upgrade pip
	$(PIP) install -e .[dev]

test:
	$(PYTEST) -q

run:
	$(VENV)/bin/ai-wm serve --host 127.0.0.1 --port 8080

api:
	$(UVICORN) ai_watermark_toolkit.api.fastapi_app:app --host 127.0.0.1 --port 8080 --reload

build:
	$(VENV)/bin/python -m build

clean:
	rm -rf .venv build dist *.egg-info .pytest_cache

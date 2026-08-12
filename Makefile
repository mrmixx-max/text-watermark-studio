PYTHON ?= python
VENV ?= .venv
ifeq ($(OS),Windows_NT)
VENV_BIN := $(VENV)/Scripts
else
VENV_BIN := $(VENV)/bin
endif
PIP := $(VENV_BIN)/pip
PYTEST := $(VENV_BIN)/pytest
UVICORN := $(VENV_BIN)/uvicorn

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
	$(VENV_BIN)/ai-wm serve --host 127.0.0.1 --port 8080

api:
	$(UVICORN) ai_watermark_toolkit.api.fastapi_app:app --host 127.0.0.1 --port 8080 --reload

build:
	$(VENV_BIN)/python -m build

clean:
	rm -rf .venv build dist *.egg-info .pytest_cache

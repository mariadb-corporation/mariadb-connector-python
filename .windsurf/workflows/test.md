---
description: Rebuild the C extension, run type checking, and run the full integration test suite
---

# Build & Verify

All commands use the project root as working directory and the `.venv` virtualenv.
pytest and mypy configuration lives in `pyproject.toml`.

## Steps

1. **Rebuild the C extension** in editable mode.
   Run from cwd `mariadb-c/`:
// turbo
```bash
.venv/bin/pip install -e mariadb-c/ --no-build-isolation 2>&1 | tail -5
```

2. **Install the pure-Python package** in editable mode.
   Run from project root:
// turbo
```bash
.venv/bin/pip install -e . --no-build-isolation 2>&1 | tail -5
```

3. **Run mypy** (config in `[tool.mypy]` of `pyproject.toml`).
   Run from project root:
// turbo
```bash
.venv/bin/python -m mypy mariadb/ --ignore-missing-imports --no-error-summary 2>&1 | tail -20
```

4. **Run integration tests — pure Python driver**.
   Run from project root:
// turbo
```bash
MARIADB_PYTHON_CONNECTOR=python .venv/bin/python -m pytest tests/integration/ --tb=short -q 2>&1 | tail -5
```

5. **Run integration tests — C extension driver**.
   Run from project root:
// turbo
```bash
MARIADB_PYTHON_CONNECTOR=c .venv/bin/python -m pytest tests/integration/ --tb=short -q 2>&1 | tail -5
```

6. **Report results**: summarise pass/fail counts for both drivers and any mypy errors. Stop on first failure.

---
description: Clone SQLAlchemy into a subfolder and run the full test suite against the local MariaDB instance
---

# SQLAlchemy Test Suite

Uses the SQLAlchemy checkout at `/home/kolz/projects/sqlalchemy` (already at `rel_2_0` with
MariaDB patches applied).  If that directory does not exist, clones it first.

DB credentials come from env vars (`TEST_DB_HOST`, `TEST_DB_PORT`, `TEST_DB_USER`,
`TEST_DB_PASSWORD`, `TEST_DB`) with sensible defaults (root@127.0.0.1:3306/test).

SQLALCHEMY_DIR is set to `/home/kolz/projects/sqlalchemy`.

## Steps

1. **Rebuild the C extension** in editable mode, from the project root.
// turbo
```bash
.venv/bin/pip install -e mariadb-c/ --no-build-isolation 2>&1 | tail -3
```

2. **Clone SQLAlchemy** `rel_2_0` if not already present, and apply the MariaDB patches.
```bash
if [ ! -d /home/kolz/projects/sqlalchemy ]; then
  git clone --depth=1 --branch rel_2_0 https://github.com/sqlalchemy/sqlalchemy.git /home/kolz/projects/sqlalchemy
  bash .github/scripts/apply-sqlalchemy-patches.sh /home/kolz/projects/sqlalchemy
fi
```

3. **Install test dependencies** into the venv (SQLAlchemy editable install + pytest).
// turbo
```bash
.venv/bin/pip install -e /home/kolz/projects/sqlalchemy pytest typing_extensions 2>&1 | tail -3
```

4. **Drop and recreate the test databases** to ensure a clean state.
// turbo
```bash
mariadb -u ${TEST_DB_USER:-root} -h ${TEST_DB_HOST:-127.0.0.1} -P ${TEST_DB_PORT:-3306} \
  -e "DROP DATABASE IF EXISTS \`${TEST_DB:-test}\`; CREATE DATABASE \`${TEST_DB:-test}\`;
      DROP DATABASE IF EXISTS \`test_schema\`; CREATE DATABASE \`test_schema\`;"
```

5. **Run the full SQLAlchemy backend test suite — C extension driver**.
   Run from `/home/kolz/projects/sqlalchemy`.
   Note: do NOT use `-x` (stop-on-first-fail) — it causes false positives from test-ordering artifacts.
   Known pre-existing failures (MariaDB 12.2 server behavior, not our connector):
   - `VersioningTest::test_basic` and `test_versioncheck` — errno 1020 instead of 0 rows matched.
```bash
/home/kolz/projects/mariadb-connector-python/.venv/bin/python -m pytest \
  "--dburi=mariadb+mariadbconnector://${TEST_DB_USER:-root}:${TEST_DB_PASSWORD:-}@${TEST_DB_HOST:-127.0.0.1}:${TEST_DB_PORT:-3306}/${TEST_DB:-test}" \
  --backend-only \
  -k "not ((TimeTest or DateTest) and test_select_direct) and not test_case_sensitive_column_constraint_reflection" \
  -p no:randomly --tb=short -q 2>&1 | tail -5
```

6. **Run a specific test** (e.g. `test_alias_pathing`) — useful for targeted debugging.
   Run from `/home/kolz/projects/sqlalchemy`:
```bash
/home/kolz/projects/mariadb-connector-python/.venv/bin/python -m pytest -xvs \
  "--dburi=mariadb+mariadbconnector://${TEST_DB_USER:-root}:${TEST_DB_PASSWORD:-}@${TEST_DB_HOST:-127.0.0.1}:${TEST_DB_PORT:-3306}/${TEST_DB:-test}" \
  -k "test_alias_pathing" --tb=long 2>&1 | tail -40
```

7. **Report results**: summarise pass/fail counts and any tracebacks. Stop on first failure.

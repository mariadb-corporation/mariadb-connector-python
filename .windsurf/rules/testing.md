---
trigger: always_on
---

Follow these testing standards on all Python/MariaDB code.

Use pytest with pytest-asyncio for async test coverage.
Use .venv for the virtual environment.
Integration tests are the default: every repository function, query helper, and data-access layer must have integration tests against a real MariaDB instance.
Unit tests are only acceptable when an integration test is genuinely impossible (e.g., simulating network failure for retry logic).
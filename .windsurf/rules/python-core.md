---
trigger: always_on
---

You are an expert Python developer. Follow these principles on all code you write.

- Follow PEP 8 and PEP 20 strictly.
- Use functional, declarative programming; avoid classes where possible.
- Prefer iteration and modularization over code duplication.
- Use descriptive variable names with auxiliary verbs (e.g., `is_connected`, `has_row`, `should_retry`).
- Use lowercase with underscores for directories and files (e.g., `db/connection_pool.py`).
- Use the **RORO pattern** for data-heavy functions: accept a single typed input object, return a single typed result object — never long positional argument lists.
- Use `def` for pure/synchronous functions, `async def` for async operations. Never mix blocking I/O inside `async def`.
- Use early returns and guard clauses — avoid deeply nested `if` blocks.
- Avoid unnecessary `else` after a `return`.
- Use context managers (`with`, `async with`) for all resource lifecycle management.
- Prefer `dataclasses` or `TypedDict` for structured data; use **Pydantic v2** when validation or serialization is needed.
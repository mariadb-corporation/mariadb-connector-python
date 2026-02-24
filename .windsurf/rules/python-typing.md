---
trigger: always_on
---

Type hints are mandatory on all Python code.

- Annotate every function signature (parameters + return type), every variable, and every class attribute. No exceptions, including internal helpers.
- Use `from __future__ import annotations` at the top of every module.
- Prefer `-> None` over omitting the return type. Use `-> Never` for functions that always raise.
- Leverage `typing` / `collections.abc` for complex types: `Sequence`, `Mapping`, `AsyncIterator`, `Callable`, `TypeVar`, `Generic`.
- Use `TypeAlias` for reused complex types (e.g., `Row: TypeAlias = dict[str, Any]`).
- Run `mypy --strict` (or `pyright`) in CI — type errors are treated as build failures, not warnings.
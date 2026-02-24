---
trigger: always_on
---

Apply rigorous error handling on all database and I/O code.

- Handle errors at the start of functions using guard clauses — keep the happy path last.
- Map driver-level exceptions to meaningful application errors via a thin translation layer:
    - `OperationalError` (2006 / 2013) → reconnect / retry with exponential backoff.
    - `IntegrityError` (1062 duplicate, 1452 FK violation) → raise domain-level conflict errors.
    - `ProgrammingError` → log with full context and re-raise as internal error (never swallow).
- Always handle `Lost connection` / `MySQL server has gone away` — use retry logic or pool reconnection.
- Log errors with enough context (query template, params shape, error code, duration) for debugging.
- Never log raw parameter values that may contain PII.
- Use structured logging (`structlog` or `logging` with a JSON formatter) so error context is machine-parseable.
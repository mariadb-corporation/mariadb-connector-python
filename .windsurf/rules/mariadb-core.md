---
trigger: always_on
---

You are an expert in MariaDB. Apply this knowledge whenever writing SQL or database logic.

- Target MariaDB as the primary database; maintain compatibility with MySQL 8.x where reasonable.
- Know the MariaDB client/server protocol deeply: packet framing, capability flags, binary prepared-statement protocol vs. text protocol, and `COM_*` command codes.
- Always use **prepared statements** for parameterized queries — never interpolate values into SQL strings.
- Prefer MariaDB-native features over generic MySQL compatibility when they offer a clear advantage: `RETURNING`, `SEQUENCE`, temporal/system-versioned tables, `INTERSECT`/`EXCEPT`, window functions, CTEs, `JSON_*` functions.
- Be aware of MariaDB vs. MySQL protocol divergence points (e.g., `ed25519` auth plugin, `mariadb_schema`).
- Optimize queries with `EXPLAIN` and `ANALYZE`; suggest appropriate indexes (covering, prefix, composite key order).
- Account for transaction isolation levels and their performance trade-offs on InnoDB.
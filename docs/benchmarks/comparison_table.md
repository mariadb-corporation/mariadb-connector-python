| Benchmark | mariadb – C extension | mariadb – pure Python | PyMySQL – pure Python | mysql-connector – C | mysql-connector – pure Python |
|---|---|---|---|---|---|
| DO 1 — command round-trip | 98,124 ops/s (1.0x) | 100,670 ops/s **(fastest)** | 88,117 ops/s (1.1x) | 53,440 ops/s (1.9x) | 31,392 ops/s (3.2x) |
| SELECT 1 — simple query | 82,928 ops/s **(fastest)** | 49,608 ops/s (1.7x) | 43,062 ops/s (1.9x) | 34,732 ops/s (2.4x) | 18,453 ops/s (4.5x) |
| INSERT — mixed types (single row) | 32,349 ops/s **(fastest)** | 29,095 ops/s (1.1x) | 27,518 ops/s (1.2x) | 30,446 ops/s (1.1x) | 18,123 ops/s (1.8x) |
| Batch INSERT — 100 rows (executemany) | 8,092 ops/s **(fastest)** | 6,192 ops/s (1.3x) | 2,147 ops/s (3.8x) | 2,337 ops/s (3.5x) | 1,834 ops/s (4.4x) |
| SELECT 1000 rows — binary protocol | 5,629 ops/s **(fastest)** | 1,509 ops/s (3.7x) | – | 1,516 ops/s (3.7x) | 294 ops/s (19.1x) |
| SELECT 1000 rows — text protocol | 6,580 ops/s **(fastest)** | 1,802 ops/s (3.7x) | 538 ops/s (12.2x) | 1,769 ops/s (3.7x) | 358 ops/s (18.4x) |
| SELECT 100 columns — binary protocol | 13,406 ops/s **(fastest)** | 5,842 ops/s (2.3x) | – | 5,750 ops/s (2.3x) | 1,221 ops/s (11.0x) |
| SELECT 100 columns — text protocol | 17,655 ops/s **(fastest)** | 6,859 ops/s (2.6x) | 2,560 ops/s (6.9x) | 7,267 ops/s (2.4x) | 2,413 ops/s (7.3x) |
| DO 1000 params — binary protocol | 3,398 ops/s **(fastest)** | 1,762 ops/s (1.9x) | – | 79 ops/s (43.2x) | 63 ops/s (54.3x) |
| DO 1000 params — text protocol | 4,008 ops/s **(fastest)** | 3,929 ops/s (1.0x) | 2,219 ops/s (1.8x) | 2,858 ops/s (1.4x) | 1,072 ops/s (3.7x) |
| Batch INSERT — 10,000 rows (executemany) | 49 ops/s (1.1x) | 54 ops/s **(fastest)** | 15 ops/s (3.6x) | 15 ops/s (3.6x) | 8 ops/s (7.1x) |
| 50 threads: connect + query + close | 280 ops/s **(fastest)** | 156 ops/s (1.8x) | 146 ops/s (1.9x) | 166 ops/s (1.7x) | 74 ops/s (3.8x) |
| 500 queries from 20 threads through a 5–20 pool | 56 ops/s **(fastest)** | 29 ops/s (1.9x) | – | 21 ops/s (2.6x) | 9 ops/s (6.4x) |

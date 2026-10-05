| Benchmark | mariadb – C extension | mariadb – pure Python | PyMySQL – pure Python | mysql-connector – C | mysql-connector – pure Python |
|---|---|---|---|---|---|
| DO 1 — command round-trip | 91,279 ops/s (1.1x) | 97,907 ops/s **(fastest)** | 84,372 ops/s (1.2x) | 49,408 ops/s (2.0x) | 26,432 ops/s (3.7x) |
| SELECT 1 — simple query | 77,241 ops/s **(fastest)** | 44,895 ops/s (1.7x) | 39,677 ops/s (1.9x) | 32,288 ops/s (2.4x) | 17,368 ops/s (4.4x) |
| INSERT — mixed types (single row) | 29,450 ops/s **(fastest)** | 28,185 ops/s (1.0x) | 26,078 ops/s (1.1x) | 27,133 ops/s (1.1x) | 17,003 ops/s (1.7x) |
| Batch INSERT — 100 rows (executemany) | 7,511 ops/s **(fastest)** | 6,213 ops/s (1.2x) | 2,048 ops/s (3.7x) | 2,276 ops/s (3.3x) | 1,794 ops/s (4.2x) |
| SELECT 1000 rows — binary protocol | 5,216 ops/s **(fastest)** | 1,390 ops/s (3.8x) | – | 1,362 ops/s (3.8x) | 279 ops/s (18.7x) |
| SELECT 1000 rows — text protocol | 5,745 ops/s **(fastest)** | 1,674 ops/s (3.4x) | 511 ops/s (11.3x) | 1,515 ops/s (3.8x) | 340 ops/s (16.9x) |
| SELECT 100 columns — binary protocol | 11,287 ops/s **(fastest)** | 5,357 ops/s (2.1x) | – | 5,107 ops/s (2.2x) | 1,177 ops/s (9.6x) |
| SELECT 100 columns — text protocol | 14,771 ops/s **(fastest)** | 6,654 ops/s (2.2x) | 2,249 ops/s (6.6x) | 6,410 ops/s (2.3x) | 2,307 ops/s (6.4x) |
| DO 1000 params — binary protocol | 2,292 ops/s **(fastest)** | 1,310 ops/s (1.7x) | – | 73 ops/s (31.6x) | 58 ops/s (39.5x) |
| DO 1000 params — text protocol | 3,647 ops/s **(fastest)** | 3,561 ops/s (1.0x) | 2,063 ops/s (1.8x) | 2,431 ops/s (1.5x) | 1,034 ops/s (3.5x) |
| Batch INSERT — 10,000 rows (executemany) | 43 ops/s (1.2x) | 50 ops/s **(fastest)** | 14 ops/s (3.7x) | 14 ops/s (3.5x) | 7 ops/s (7.2x) |
| 50 threads: connect + query + close | 249 ops/s **(fastest)** | 149 ops/s (1.7x) | 124 ops/s (2.0x) | 146 ops/s (1.7x) | 65 ops/s (3.8x) |
| 500 queries from 20 threads through a 5–20 pool | 52 ops/s **(fastest)** | 27 ops/s (2.0x) | – | 20 ops/s (2.6x) | 8 ops/s (6.3x) |

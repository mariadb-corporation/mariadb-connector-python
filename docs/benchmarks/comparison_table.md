| Benchmark | mariadb – C extension | mariadb – pure Python | PyMySQL – pure Python | mysql-connector – C | mysql-connector – pure Python |
|---|---|---|---|---|---|
| DO 1 — command round-trip | 101,379 ops/s (1.0x) | 105,469 ops/s **(fastest)** | 92,207 ops/s (1.1x) | 54,052 ops/s (2.0x) | 31,207 ops/s (3.4x) |
| SELECT 1 — simple query | 84,663 ops/s **(fastest)** | 49,212 ops/s (1.7x) | 43,138 ops/s (2.0x) | 34,163 ops/s (2.5x) | 18,215 ops/s (4.6x) |
| INSERT — mixed types (single row) | 33,404 ops/s **(fastest)** | 27,108 ops/s (1.2x) | 27,623 ops/s (1.2x) | 29,880 ops/s (1.1x) | 17,617 ops/s (1.9x) |
| Batch INSERT — 100 rows (executemany) | 8,023 ops/s **(fastest)** | 6,529 ops/s (1.2x) | 2,157 ops/s (3.7x) | 2,355 ops/s (3.4x) | 1,787 ops/s (4.5x) |
| SELECT 1000 rows — binary protocol | 5,670 ops/s **(fastest)** | 1,246 ops/s (4.6x) | – | 1,495 ops/s (3.8x) | 288 ops/s (19.7x) |
| SELECT 1000 rows — text protocol | 6,522 ops/s **(fastest)** | 1,464 ops/s (4.5x) | 534 ops/s (12.2x) | 1,754 ops/s (3.7x) | 354 ops/s (18.4x) |
| SELECT 100 columns — binary protocol | 13,065 ops/s **(fastest)** | 6,053 ops/s (2.2x) | – | 5,501 ops/s (2.4x) | 1,221 ops/s (10.7x) |
| SELECT 100 columns — text protocol | 17,013 ops/s **(fastest)** | 6,929 ops/s (2.5x) | 2,533 ops/s (6.7x) | 7,126 ops/s (2.4x) | 2,373 ops/s (7.2x) |
| DO 1000 params — binary protocol | 2,747 ops/s **(fastest)** | 1,365 ops/s (2.0x) | – | 79 ops/s (35.0x) | 61 ops/s (44.7x) |
| DO 1000 params — text protocol | 4,027 ops/s (1.0x) | 4,031 ops/s **(fastest)** | 2,208 ops/s (1.8x) | 2,850 ops/s (1.4x) | 1,075 ops/s (3.7x) |
| Batch INSERT — 10,000 rows (executemany) | 47 ops/s (1.1x) | 52 ops/s **(fastest)** | 15 ops/s (3.5x) | 15 ops/s (3.5x) | 8 ops/s (6.9x) |
| 50 threads: connect + query + close | 273 ops/s **(fastest)** | 160 ops/s (1.7x) | 141 ops/s (1.9x) | 153 ops/s (1.8x) | 72 ops/s (3.8x) |
| 500 queries from 20 threads through a 5–20 pool | 54 ops/s **(fastest)** | 30 ops/s (1.8x) | – | 21 ops/s (2.6x) | 9 ops/s (6.4x) |

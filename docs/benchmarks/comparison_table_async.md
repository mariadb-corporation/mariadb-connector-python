| Benchmark | mariadb – C extension (async) | mariadb – pure Python (async) | asyncmy – C (Cython) | aiomysql – pure Python |
|---|---|---|---|---|
| DO 1 — command round-trip | 31,971 ops/s (1.1x) | 32,198 ops/s (1.1x) | 33,879 ops/s **(fastest)** | 31,587 ops/s (1.1x) |
| SELECT 1 — simple query | 27,874 ops/s **(fastest)** | 22,920 ops/s (1.2x) | 23,539 ops/s (1.2x) | 19,941 ops/s (1.4x) |
| Batch INSERT — 100 rows (executemany) | 5,822 ops/s **(fastest)** | 5,146 ops/s (1.1x) | 2,261 ops/s (2.6x) | 2,024 ops/s (2.9x) |
| Batch INSERT — 10,000 rows (executemany) | 48 ops/s (1.1x) | 53 ops/s **(fastest)** | 19 ops/s (2.8x) | 16 ops/s (3.4x) |
| SELECT 1000 rows | 3,078 ops/s (1.9x) | 1,636 ops/s (3.6x) | 5,872 ops/s **(fastest)** | 457 ops/s (12.9x) |
| SELECT 100 columns | 11,997 ops/s **(fastest)** | 5,943 ops/s (2.0x) | 5,244 ops/s (2.3x) | 2,184 ops/s (5.5x) |
| DO 1000 params | 3,624 ops/s (1.0x) | 3,643 ops/s **(fastest)** | 3,020 ops/s (1.2x) | 2,393 ops/s (1.5x) |
| 50 concurrent connect + query + close | 239 ops/s **(fastest)** | 130 ops/s (1.8x) | 162 ops/s (1.5x) | 138 ops/s (1.7x) |
| 500 concurrent queries through a 5–20 pool | 36 ops/s **(fastest)** | 25 ops/s (1.4x) | 9 ops/s (3.8x) | 17 ops/s (2.1x) |

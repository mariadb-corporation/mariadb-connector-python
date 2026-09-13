| Benchmark | mariadb – C extension (async) | mariadb – pure Python (async) | asyncmy – C (Cython) | aiomysql – pure Python |
|---|---|---|---|---|
| DO 1 — command round-trip | 29,774 ops/s (1.1x) | 30,666 ops/s (1.0x) | 32,040 ops/s **(fastest)** | 29,820 ops/s (1.1x) |
| SELECT 1 — simple query | 26,141 ops/s **(fastest)** | 21,739 ops/s (1.2x) | 22,231 ops/s (1.2x) | 18,968 ops/s (1.4x) |
| Batch INSERT — 100 rows (executemany) | 5,502 ops/s **(fastest)** | 4,784 ops/s (1.2x) | 2,144 ops/s (2.6x) | 1,945 ops/s (2.8x) |
| Batch INSERT — 10,000 rows (executemany) | 44 ops/s (1.1x) | 50 ops/s **(fastest)** | 18 ops/s (2.7x) | 15 ops/s (3.4x) |
| SELECT 1000 rows | 2,783 ops/s (2.0x) | 1,256 ops/s (4.3x) | 5,446 ops/s **(fastest)** | 420 ops/s (13.0x) |
| SELECT 100 columns | 11,677 ops/s **(fastest)** | 5,588 ops/s (2.1x) | 4,894 ops/s (2.4x) | 2,072 ops/s (5.6x) |
| DO 1000 params | 3,471 ops/s **(fastest)** | 3,446 ops/s (1.0x) | 2,895 ops/s (1.2x) | 2,389 ops/s (1.5x) |
| 50 concurrent connect + query + close | 224 ops/s **(fastest)** | 121 ops/s (1.9x) | 152 ops/s (1.5x) | 130 ops/s (1.7x) |
| 500 concurrent queries through a 5–20 pool | 35 ops/s **(fastest)** | 24 ops/s (1.5x) | 9 ops/s (3.9x) | 16 ops/s (2.2x) |

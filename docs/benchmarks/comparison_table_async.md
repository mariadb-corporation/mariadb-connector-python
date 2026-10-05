| Benchmark | mariadb – C extension (async) | mariadb – pure Python (async) | asyncmy – C (Cython) | aiomysql – pure Python |
|---|---|---|---|---|
| DO 1 — command round-trip | 30,256 ops/s (1.1x) | 31,446 ops/s (1.1x) | 33,963 ops/s **(fastest)** | 29,839 ops/s (1.1x) |
| SELECT 1 — simple query | 26,118 ops/s **(fastest)** | 20,667 ops/s (1.3x) | 22,727 ops/s (1.1x) | 19,509 ops/s (1.3x) |
| Batch INSERT — 100 rows (executemany) | 5,027 ops/s (1.0x) | 5,142 ops/s **(fastest)** | 2,209 ops/s (2.3x) | 1,964 ops/s (2.6x) |
| Batch INSERT — 10,000 rows (executemany) | 44 ops/s (1.2x) | 52 ops/s **(fastest)** | 18 ops/s (2.9x) | 15 ops/s (3.4x) |
| SELECT 1000 rows | 2,678 ops/s (2.1x) | 1,624 ops/s (3.5x) | 5,652 ops/s **(fastest)** | 430 ops/s (13.1x) |
| SELECT 100 columns | 11,989 ops/s **(fastest)** | 5,783 ops/s (2.1x) | 4,497 ops/s (2.7x) | 2,118 ops/s (5.7x) |
| DO 1000 params | 3,504 ops/s (1.0x) | 3,642 ops/s **(fastest)** | 2,818 ops/s (1.3x) | 2,404 ops/s (1.5x) |
| 50 concurrent connect + query + close | 226 ops/s **(fastest)** | 125 ops/s (1.8x) | 154 ops/s (1.5x) | 130 ops/s (1.7x) |
| 500 concurrent queries through a 5–20 pool | 36 ops/s **(fastest)** | 25 ops/s (1.4x) | 9 ops/s (4.0x) | 16 ops/s (2.2x) |

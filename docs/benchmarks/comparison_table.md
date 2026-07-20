| Benchmark | mariadb – C extension | mariadb – pure Python | PyMySQL | mysql-connector – C | mysql-connector – pure |
|---|---|---|---|---|---|
| DO 1 — command round-trip | 103,634 ops/s (1.0x) | 104,329 ops/s **(fastest)** | 89,333 ops/s (1.2x) | 50,807 ops/s (2.1x) | 28,999 ops/s (3.6x) |
| SELECT 1 — simple query | 84,748 ops/s **(fastest)** | 50,886 ops/s (1.7x) | 42,994 ops/s (2.0x) | 33,837 ops/s (2.5x) | 18,129 ops/s (4.7x) |
| INSERT — mixed types (single row) | 34,520 ops/s **(fastest)** | 30,123 ops/s (1.1x) | 26,227 ops/s (1.3x) | 29,508 ops/s (1.2x) | 17,484 ops/s (2.0x) |
| Batch INSERT — 100 rows (executemany) | 8,371 ops/s **(fastest)** | 5,371 ops/s (1.6x) | 2,126 ops/s (3.9x) | 2,378 ops/s (3.5x) | 1,871 ops/s (4.5x) |
| SELECT 1000 rows — binary protocol | 6,159 ops/s **(fastest)** | 837 ops/s (7.4x) | – | 1,442 ops/s (4.3x) | 281 ops/s (21.9x) |
| SELECT 1000 rows — text protocol | 6,649 ops/s **(fastest)** | 1,017 ops/s (6.5x) | 529 ops/s (12.6x) | 1,562 ops/s (4.3x) | 340 ops/s (19.6x) |
| SELECT 100 columns — binary protocol | 13,600 ops/s **(fastest)** | 6,013 ops/s (2.3x) | – | 5,451 ops/s (2.5x) | 1,205 ops/s (11.3x) |
| SELECT 100 columns — text protocol | 18,028 ops/s **(fastest)** | 7,226 ops/s (2.5x) | 2,526 ops/s (7.1x) | 6,847 ops/s (2.6x) | 2,326 ops/s (7.7x) |
| DO 1000 params — binary protocol | 2,787 ops/s **(fastest)** | 1,364 ops/s (2.0x) | – | 75 ops/s (37.1x) | 58 ops/s (48.4x) |
| DO 1000 params — text protocol | 4,087 ops/s **(fastest)** | 4,001 ops/s (1.0x) | 2,223 ops/s (1.8x) | 2,787 ops/s (1.5x) | 1,049 ops/s (3.9x) |

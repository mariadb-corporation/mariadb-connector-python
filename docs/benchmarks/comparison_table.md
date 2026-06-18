| Benchmark | mariadb – C extension | mariadb – pure Python | PyMySQL | mysql-connector – C | mysql-connector – pure |
|---|---|---|---|---|---|
| DO 1 — command round-trip | 65,828 ops/s **(fastest)** | 60,869 ops/s (1.1x) | 59,863 ops/s (1.1x) | 33,994 ops/s (1.9x) | 23,257 ops/s (2.8x) |
| SELECT 1 — simple query | 50,155 ops/s **(fastest)** | 31,623 ops/s (1.6x) | 30,522 ops/s (1.6x) | 23,906 ops/s (2.1x) | 14,770 ops/s (3.4x) |
| INSERT — mixed types (single row) | 22,398 ops/s **(fastest)** | 20,125 ops/s (1.1x) | 19,846 ops/s (1.1x) | 21,392 ops/s (1.0x) | 14,755 ops/s (1.5x) |
| Batch INSERT — 100 rows (executemany) | 6,110 ops/s **(fastest)** | 4,786 ops/s (1.3x) | 1,880 ops/s (3.3x) | 2,050 ops/s (3.0x) | 1,626 ops/s (3.8x) |
| SELECT 1000 rows — binary protocol | 5,672 ops/s **(fastest)** | 713 ops/s (8.0x) | – | 1,289 ops/s (4.4x) | 22 ops/s (255.7x) |
| SELECT 1000 rows — text protocol | 5,220 ops/s **(fastest)** | 854 ops/s (6.1x) | 444 ops/s (11.8x) | 1,429 ops/s (3.7x) | 298 ops/s (17.5x) |
| SELECT 100 columns — binary protocol | 19,782 ops/s **(fastest)** | 13,489 ops/s (1.5x) | – | 4,139 ops/s (4.8x) | 24 ops/s (832.1x) |
| SELECT 100 columns — text protocol | 13,910 ops/s **(fastest)** | 5,290 ops/s (2.6x) | 2,120 ops/s (6.6x) | 5,568 ops/s (2.5x) | 2,088 ops/s (6.7x) |
| DO 1000 params — binary protocol | 4,268 ops/s **(fastest)** | 1,977 ops/s (2.2x) | – | 74 ops/s (58.0x) | 17 ops/s (246.5x) |
| DO 1000 params — text protocol | 3,560 ops/s **(fastest)** | 3,415 ops/s (1.0x) | 1,748 ops/s (2.0x) | 2,485 ops/s (1.4x) | 860 ops/s (4.1x) |

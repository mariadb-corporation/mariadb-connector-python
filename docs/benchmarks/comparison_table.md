| Benchmark | mariadb – C extension | mariadb – pure Python | PyMySQL | mysql-connector – C | mysql-connector – pure |
|---|---|---|---|---|---|
| DO 1 — command round-trip | 101,753 ops/s (1.0x) | 103,308 ops/s **(fastest)** | 91,890 ops/s (1.1x) | 52,438 ops/s (2.0x) | 31,414 ops/s (3.3x) |
| SELECT 1 — simple query | 85,508 ops/s **(fastest)** | 52,596 ops/s (1.6x) | 43,679 ops/s (2.0x) | 34,932 ops/s (2.4x) | 18,266 ops/s (4.7x) |
| INSERT — mixed types (single row) | 34,305 ops/s **(fastest)** | 30,269 ops/s (1.1x) | 26,165 ops/s (1.3x) | 30,360 ops/s (1.1x) | 17,693 ops/s (1.9x) |
| Batch INSERT — 100 rows (executemany) | 8,454 ops/s **(fastest)** | 5,394 ops/s (1.6x) | 2,141 ops/s (3.9x) | 2,370 ops/s (3.6x) | 1,885 ops/s (4.5x) |
| SELECT 1000 rows — binary protocol | 6,259 ops/s **(fastest)** | 818 ops/s (7.7x) | – | 1,490 ops/s (4.2x) | 287 ops/s (21.8x) |
| SELECT 1000 rows — text protocol | 6,781 ops/s **(fastest)** | 1,049 ops/s (6.5x) | 541 ops/s (12.5x) | 1,633 ops/s (4.2x) | 355 ops/s (19.1x) |
| SELECT 100 columns — binary protocol | 13,624 ops/s **(fastest)** | 6,170 ops/s (2.2x) | – | 5,511 ops/s (2.5x) | 1,230 ops/s (11.1x) |
| SELECT 100 columns — text protocol | 18,113 ops/s **(fastest)** | 7,435 ops/s (2.4x) | 2,543 ops/s (7.1x) | 7,303 ops/s (2.5x) | 2,362 ops/s (7.7x) |
| DO 1000 params — binary protocol | 2,721 ops/s **(fastest)** | 1,394 ops/s (2.0x) | – | 76 ops/s (35.8x) | 59 ops/s (46.2x) |
| DO 1000 params — text protocol | 4,082 ops/s **(fastest)** | 4,066 ops/s (1.0x) | 2,187 ops/s (1.9x) | 2,870 ops/s (1.4x) | 1,100 ops/s (3.7x) |

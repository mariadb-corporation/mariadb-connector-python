# Benchmark

```
pip install mysql-connector-python pyperf
python bench_mariadb.py -o mariadb_bench.json --inherit-environ=TEST_USER,TEST_HOST,TEST_PORT
python bench_mysql.py -o mysql_bench.json --inherit-environ=TEST_USER,TEST_HOST,TEST_PORT
```

Results are available to pyperf json format

An example of  
```
>python -m pyperf compare_to mysql_bench.json mariadb_bench.json --table
+----------------------------------------------------+-------------+------------------------------+
| Benchmark                                          | mysql_bench | mariadb_bench                |
+====================================================+=============+==============================+
| do 1                                               | 114 us      | 45.4 us: 2.50x faster (-60%) |
+----------------------------------------------------+-------------+------------------------------+
| select 1                                           | 209 us      | 57.3 us: 3.65x faster (-73%) |
+----------------------------------------------------+-------------+------------------------------+
| select 1 mysql user                                | 1.04 ms     | 122 us: 8.52x faster (-88%)  |
+----------------------------------------------------+-------------+------------------------------+
| Select <10 cols of 100 chars> from_seq_1_to_100000 | 323 ms      | 35.0 ms: 9.22x faster (-89%) |
+----------------------------------------------------+-------------+------------------------------+```

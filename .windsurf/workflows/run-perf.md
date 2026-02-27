* Use .venv for the virtual environment.
* build mariadb-c
* run the benchmark test suite `make bench-fast` in benchmarks directory
* run the benchmark with previous version too, to compare results
* ensure to set `sudo cpupower frequency-set --governor performance` before running the benchmarks
* ensure to set `sudo cpupower frequency-set --governor powersave` after running the benchmarks


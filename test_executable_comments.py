#!/usr/bin/env python3
"""Quick test for executable comment handling"""

from mariadb.impl.sql_parser import split_sql_parts

# Test 1: Regular comment - should ignore placeholder
sql1 = "SELECT /* ignore ? */ * FROM users WHERE id = ?"
sql_bytes1, positions1 = split_sql_parts(sql1)
print(f"Test 1 - Regular comment:")
print(f"  SQL: {sql1}")
print(f"  Positions: {positions1}")
print(f"  Expected: [50, 51] (only the last ?)")
print(f"  Result: {'PASS' if positions1 == [50, 51] else 'FAIL'}")
print()

# Test 2: Executable comment /*! */ - should find placeholder
sql2 = "INSERT /*! IGNORE */ INTO users VALUES (?)"
sql_bytes2, positions2 = split_sql_parts(sql2)
print(f"Test 2 - Executable comment /*!:")
print(f"  SQL: {sql2}")
print(f"  Positions: {positions2}")
print(f"  Expected: [41, 42]")
print(f"  Result: {'PASS' if positions2 == [41, 42] else 'FAIL'}")
print()

# Test 3: MariaDB executable comment /*M! */ - should find placeholder
sql3 = "SELECT /*M! 100100 SQL_NO_CACHE */ * FROM users WHERE id = ?"
sql_bytes3, positions3 = split_sql_parts(sql3)
print(f"Test 3 - MariaDB executable comment /*M!:")
print(f"  SQL: {sql3}")
print(f"  Positions: {positions3}")
print(f"  Expected: [60, 61]")
print(f"  Result: {'PASS' if positions3 == [60, 61] else 'FAIL'}")
print()

# Test 4: Mixed - regular and executable comments
sql4 = "SELECT /* ignore ? */ * FROM users /*! keep ? */ WHERE id = ?"
sql_bytes4, positions4 = split_sql_parts(sql4)
print(f"Test 4 - Mixed comments:")
print(f"  SQL: {sql4}")
print(f"  Positions: {positions4}")
print(f"  Expected: [44, 45, 60, 61] (2 placeholders: in /*! */ and after WHERE)")
print(f"  Result: {'PASS' if positions4 == [44, 45, 60, 61] else 'FAIL'}")

#!/usr/bin/env python3
"""Verify the complete native_object test"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set test environment variables
if 'TEST_DB_USER' not in os.environ:
    os.environ['TEST_DB_USER'] = 'root'
if 'TEST_DB_HOST' not in os.environ:
    os.environ['TEST_DB_HOST'] = '127.0.0.1'
if 'TEST_DB_DATABASE' not in os.environ:
    os.environ['TEST_DB_DATABASE'] = 'testp'
if 'TEST_DB_PORT' not in os.environ:
    os.environ['TEST_DB_PORT'] = '3306'

import mariadb
import uuid
import ipaddress

print("=" * 70)
print("COMPREHENSIVE NATIVE_OBJECT TEST")
print("=" * 70)

conn = mariadb.connect(
    user=os.environ['TEST_DB_USER'],
    host=os.environ['TEST_DB_HOST'],
    database=os.environ['TEST_DB_DATABASE'],
    port=int(os.environ['TEST_DB_PORT'])
)

if conn.server_version_info < (10, 10, 0):
    print("SKIP: Server version < 10.10.0")
    conn.close()
    sys.exit(0)

print(f"\n✓ Connected to MariaDB {conn.server_version}\n")

# Setup test data
cursor = conn.cursor()
cursor.execute("DROP TABLE IF EXISTS t1")
cursor.execute("CREATE TABLE t1 (a inet6, b inet4, c uuid)")

test_ipv6 = ipaddress.ip_address('2001:db8::1')
test_ipv4 = ipaddress.ip_address('192.168.1.100')
test_uuid = uuid.uuid4()

cursor.execute("INSERT INTO t1 VALUES (?, ?, ?)", (test_ipv6, test_ipv4, test_uuid))
cursor.close()

print("Test 1: Cursor-level native_object=False (default)")
print("-" * 70)
cursor = conn.cursor()
cursor.execute("SELECT a, b, c FROM t1")
row = cursor.fetchone()
print(f"  INET6: {type(row[0]).__name__:20} = {row[0]}")
print(f"  INET4: {type(row[1]).__name__:20} = {row[1]}")
print(f"  UUID:  {type(row[2]).__name__:20} = {row[2]}")
assert isinstance(row[0], str)
assert isinstance(row[1], str)
assert isinstance(row[2], str)
print("  ✓ All values are strings\n")
cursor.close()

print("Test 2: Cursor-level native_object=True")
print("-" * 70)
cursor = conn.cursor(native_object=True)
cursor.execute("SELECT a, b, c FROM t1")
row = cursor.fetchone()
print(f"  INET6: {type(row[0]).__name__:20} = {row[0]}")
print(f"  INET4: {type(row[1]).__name__:20} = {row[1]}")
print(f"  UUID:  {type(row[2]).__name__:20} = {row[2]}")
assert isinstance(row[0], (ipaddress.IPv6Address, ipaddress.IPv4Address))
assert isinstance(row[1], (ipaddress.IPv6Address, ipaddress.IPv4Address))
assert isinstance(row[2], uuid.UUID)
assert row[0] == test_ipv6
assert row[1] == test_ipv4
assert row[2] == test_uuid
print("  ✓ All values are native Python objects\n")
cursor.close()

print("Test 3: Binary protocol with native_object=True")
print("-" * 70)
cursor = conn.cursor(native_object=True, binary=True)
cursor.execute("SELECT a, b, c FROM t1")
row = cursor.fetchone()
print(f"  INET6: {type(row[0]).__name__:20} = {row[0]}")
print(f"  INET4: {type(row[1]).__name__:20} = {row[1]}")
print(f"  UUID:  {type(row[2]).__name__:20} = {row[2]}")
assert isinstance(row[0], (ipaddress.IPv6Address, ipaddress.IPv4Address))
assert isinstance(row[1], (ipaddress.IPv6Address, ipaddress.IPv4Address))
assert isinstance(row[2], uuid.UUID)
print("  ✓ Binary protocol works with native objects\n")
cursor.close()

print("Test 4: Connection-level native_object=True")
print("-" * 70)
conn_native = mariadb.connect(
    user=os.environ['TEST_DB_USER'],
    host=os.environ['TEST_DB_HOST'],
    database=os.environ['TEST_DB_DATABASE'],
    port=int(os.environ['TEST_DB_PORT']),
    native_object=True
)
cursor = conn_native.cursor()
cursor.execute("SELECT a, b, c FROM t1")
row = cursor.fetchone()
print(f"  INET6: {type(row[0]).__name__:20} = {row[0]}")
print(f"  INET4: {type(row[1]).__name__:20} = {row[1]}")
print(f"  UUID:  {type(row[2]).__name__:20} = {row[2]}")
assert isinstance(row[0], (ipaddress.IPv6Address, ipaddress.IPv4Address))
assert isinstance(row[1], (ipaddress.IPv6Address, ipaddress.IPv4Address))
assert isinstance(row[2], uuid.UUID)
print("  ✓ Connection-level setting applies to cursors\n")

print("Test 5: Cursor override of connection-level setting")
print("-" * 70)
cursor_override = conn_native.cursor(native_object=False)
cursor_override.execute("SELECT a, b, c FROM t1")
row = cursor_override.fetchone()
print(f"  INET6: {type(row[0]).__name__:20} = {row[0]}")
print(f"  INET4: {type(row[1]).__name__:20} = {row[1]}")
print(f"  UUID:  {type(row[2]).__name__:20} = {row[2]}")
assert isinstance(row[0], str)
assert isinstance(row[1], str)
assert isinstance(row[2], str)
print("  ✓ Cursor-level override works\n")

cursor_override.close()
cursor.close()
conn_native.close()

# Cleanup
cursor = conn.cursor()
cursor.execute("DROP TABLE t1")
cursor.close()
conn.close()

print("=" * 70)
print("✅ ALL TESTS PASSED!")
print("=" * 70)

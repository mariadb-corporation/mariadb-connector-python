-- Set character set for test schemas
CREATE SCHEMA IF NOT EXISTS test_schema CHARACTER SET utf8mb4;
CREATE SCHEMA IF NOT EXISTS test_schema_2 CHARACTER SET utf8mb4;

-- Install auth plugin
/*!120101 INSTALL SONAME 'auth_mysql_sha2' */;
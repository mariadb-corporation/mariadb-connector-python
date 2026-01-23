-- Set character set for test schemas
CREATE SCHEMA IF NOT EXISTS test_schema CHARACTER SET utf8mb4;
CREATE SCHEMA IF NOT EXISTS test_schema_2 CHARACTER SET utf8mb4;

-- Ensure the testp database uses utf8mb4 charset
-- This is critical for Windows where the database may be created before
-- the character-set-server configuration is applied
ALTER DATABASE testp CHARACTER SET utf8mb4;

-- Install auth plugin
/*!120101 INSTALL SONAME 'auth_mysql_sha2' */;
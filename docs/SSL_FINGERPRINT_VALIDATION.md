# SSL Fingerprint Validation

## Overview

This document describes the SSL fingerprint validation feature implemented in the MariaDB Connector/Python, which allows secure connections to MariaDB servers using self-signed certificates.

## Background

When connecting to a MariaDB server with SSL/TLS enabled but using self-signed certificates, traditional certificate validation fails because the certificate is not signed by a trusted Certificate Authority (CA). However, MariaDB provides a mechanism to validate self-signed certificates using password-based fingerprint validation.

## How It Works

### 1. SSL Handshake with Fingerprint Capture

When `ssl_verify_cert=False` is set, the connector:
- Creates an unverified SSL context (no certificate validation)
- Captures the server's certificate during the SSL handshake
- Calculates the SHA-256 fingerprint of the certificate

### 2. Authentication

The client proceeds with normal authentication using a MitM-proof authentication plugin (e.g., `mysql_native_password`, `caching_sha2_password`, `parsec`).

### 3. Server Validation Hash

After successful authentication, the server sends an OK packet containing a validation hash in the `info` field:
```
info = 0x01 + hex(SHA256(hash(password) + seed + cert_fingerprint))
```

Where:
- `0x01` = SHA-256 algorithm marker
- `hash(password)` = Authentication plugin's password hash
- `seed` = Server's authentication seed/scramble
- `cert_fingerprint` = SHA-256 of the server's certificate (DER format)

### 4. Client Validation

The client:
1. Calculates the same hash using its captured fingerprint
2. Compares it with the server's validation hash
3. Raises an error if they don't match

## Implementation

### Key Components

1. **SSLFingerprintValidator** (`mariadb/impl/client/socket/ssl_fingerprint_validator.py`)
   - Captures certificate fingerprint during SSL handshake
   - Validates fingerprint against server-provided hash

2. **OkPacket** (`mariadb/impl/message/server/ok_packet.py`)
   - Enhanced to parse and store the `info` field containing validation hash

3. **Authentication Plugins** (`mariadb/impl/plugin/authentication/`)
   - All plugins implement `is_mitm_proof()` - returns `True` for MitM-proof plugins
   - All plugins implement `hash(conf)` - returns the password hash for validation

4. **SyncClient** (`mariadb/impl/client/sync_client.py`)
   - Integrates fingerprint capture during SSL upgrade
   - Validates fingerprint in `_validate_ssl_fingerprint()` method

### Validation Flow

```python
# During SSL handshake
if not ssl_verify_cert:
    validator = SSLFingerprintValidator()
    ssl_context = validator.create_unverified_context(base_context)
    ssl_socket = ssl_context.wrap_socket(socket)
    validator.capture_fingerprint(ssl_socket)

# During authentication
auth_plugin = get_auth_plugin(...)
response = auth_plugin.process(...)

# After OK packet
ok_packet = OkPacket.decode(response)
if validator.get_fingerprint():
    auth_hash = auth_plugin.hash(configuration)
    if not validator.validate_fingerprint(auth_hash, seed, ok_packet.info):
        raise OperationalError("Fingerprint validation failed")
```

## Security Considerations

### MitM-Proof Requirements

Fingerprint validation only works with MitM-proof authentication plugins:
- ✅ `mysql_native_password` - MitM-proof
- ✅ `caching_sha2_password` - MitM-proof  
- ✅ `parsec` - MitM-proof
- ❌ `mysql_clear_password` - NOT MitM-proof (sends password in clear text)

### Password Requirement

Self-signed certificate validation **requires a password**. Connections without passwords will fail validation because:
- The validation hash depends on `hash(password)`
- Empty password = no hash = no validation

### Unix Domain Sockets

Validation is skipped for Unix domain sockets because they are inherently MitM-proof (local-only communication).

## Usage

### Basic Usage

```python
import mariadb

# Connect with self-signed certificate
conn = mariadb.connect(
    user="root",
    password="mypassword",  # Required!
    host="localhost",
    port=3306,
    ssl=True,
    ssl_verify_cert=False  # Enables fingerprint validation
)
```

### Error Scenarios

1. **No password provided**:
```
OperationalError: Self signed certificates require a password
```

2. **Non-MitM-proof plugin**:
```
OperationalError: Cannot use authentication plugin mysql_clear_password with self signed certificates
```

3. **Fingerprint mismatch**:
```
OperationalError: Self signed certificates fingerprint validation failed
```

## Comparison with Java Connector

This implementation follows the same pattern as the MariaDB Connector/J:

| Feature | Java Connector | Python Connector |
|---------|---------------|------------------|
| Fingerprint capture | `MariaDbX509EphemeralTrustingManager` | `SSLFingerprintValidator` |
| Validation location | `StandardClient.authenticationHandler()` | `SyncClient._validate_ssl_fingerprint()` |
| Hash algorithm | SHA-256 | SHA-256 |
| Validation formula | `SHA256(hash + seed + fingerprint)` | `SHA256(hash + seed + fingerprint)` |
| MitM-proof check | `authPlugin.isMitMProof()` | `auth_plugin.is_mitm_proof()` |
| Password hash | `authPlugin.hash()` | `auth_plugin.hash()` |

## Testing

To test fingerprint validation:

1. Set up MariaDB with self-signed certificate
2. Connect with `ssl_verify_cert=False`
3. Verify connection succeeds with correct password
4. Verify connection fails with wrong password or tampered certificate

## Future Enhancements

- [ ] Add async client support (`AsyncClient`)
- [ ] Add configuration option to explicitly enable/disable fingerprint validation
- [ ] Add logging for fingerprint validation steps
- [ ] Add fingerprint caching for reconnections

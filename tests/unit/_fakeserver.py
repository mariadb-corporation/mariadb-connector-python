#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
A tiny in-process MySQL/MariaDB wire-protocol fake server for unit tests.
"""

import socket
import struct
import threading
import time

# ---- capability flags -------------------------------------------------------
CLIENT_PROTOCOL_41 = 0x00000200
CLIENT_SECURE_CONNECTION = 0x00008000
CLIENT_PLUGIN_AUTH = 0x00080000
# CLIENT_SSL (0x800), CLIENT_DEPRECATE_EOF (1<<24), and the MariaDB extended
# CACHE_METADATA/EXTENDED_METADATA bits are deliberately NOT advertised.

# MariaDB extended capabilities (bits 32..63), sent as a separate 4-byte field
# in the handshake. BULK_UNIT_RESULTS = 1<<37 -> bit 5 of the extended dword.
MARIADB_CLIENT_STMT_BULK_OPERATIONS = 1 << (34 - 32)   # bit 2
MARIADB_CLIENT_BULK_UNIT_RESULTS = 1 << (37 - 32)      # bit 5

# ---- MySQL field types ------------------------------------------------------
MYSQL_TYPE_TINY = 1
MYSQL_TYPE_SHORT = 2
MYSQL_TYPE_LONG = 3
MYSQL_TYPE_FLOAT = 4
MYSQL_TYPE_DOUBLE = 5
MYSQL_TYPE_LONGLONG = 8
MYSQL_TYPE_VARCHAR = 15
MYSQL_TYPE_NEWDECIMAL = 246
MYSQL_TYPE_BLOB = 252
MYSQL_TYPE_VAR_STRING = 253
MYSQL_TYPE_STRING = 254

# ---- COM codes --------------------------------------------------------------
COM_QUIT = 0x01
COM_QUERY = 0x03
COM_STMT_PREPARE = 0x16
COM_STMT_EXECUTE = 0x17
COM_STMT_BULK_EXECUTE = 0xFA

_STATUS_AUTOCOMMIT = 0x0002


# ---------------------------------------------------------------------------
# Low-level encoders
# ---------------------------------------------------------------------------
def pkt(seq, body):
    """Frame a payload: 3-byte LE length + 1-byte sequence id."""
    return struct.pack("<I", len(body))[:3] + bytes([seq & 0xFF]) + body


def lenenc_int(n):
    if n < 251:
        return bytes([n])
    if n < 65536:
        return b"\xfc" + struct.pack("<H", n)
    if n < 16777216:
        return b"\xfd" + struct.pack("<I", n)[:3]
    return b"\xfe" + struct.pack("<Q", n)


def lenenc_str(b):
    if isinstance(b, str):
        b = b.encode("utf-8")
    return lenenc_int(len(b)) + b


def ok_body(affected_rows=0, last_insert_id=0, status=_STATUS_AUTOCOMMIT, warnings=0):
    return (b"\x00" + lenenc_int(affected_rows) + lenenc_int(last_insert_id)
            + struct.pack("<HH", status, warnings))


def eof_body(warnings=0, status=_STATUS_AUTOCOMMIT):
    # classic 5-byte EOF: 0xFE + warnings(2 LE) + status(2 LE)
    return b"\xfe" + struct.pack("<HH", warnings, status)


def err_body(errno=1064, sqlstate="42000", message="fake error"):
    return (b"\xff" + struct.pack("<H", errno) + b"#" + sqlstate.encode("ascii")
            + message.encode("utf-8"))


def column_def(name, field_type, charset=33, length=255, flags=0, decimals=0):
    """Protocol::ColumnDefinition41 (no extended metadata)."""
    return (lenenc_str("def") + lenenc_str("") + lenenc_str("") + lenenc_str("")
            + lenenc_str(name) + lenenc_str("")
            + b"\x0c" + struct.pack("<HIBHB", charset, length, field_type, flags, decimals)
            + b"\x00\x00")


def text_value(v):
    """Encode one text-protocol column value (None -> the single 0xFB NULL byte)."""
    if v is None:
        return b"\xfb"
    if isinstance(v, bool):
        v = 1 if v else 0
    return lenenc_str(str(v))


def binary_value(v, field_type):
    """Encode one binary-protocol column value (caller handles NULL via bitmap)."""
    if field_type == MYSQL_TYPE_TINY:
        return struct.pack("<b", int(v))
    if field_type == MYSQL_TYPE_SHORT:
        return struct.pack("<h", int(v))
    if field_type == MYSQL_TYPE_LONG:
        return struct.pack("<i", int(v))
    if field_type == MYSQL_TYPE_LONGLONG:
        return struct.pack("<q", int(v))
    if field_type == MYSQL_TYPE_FLOAT:
        return struct.pack("<f", float(v))
    if field_type == MYSQL_TYPE_DOUBLE:
        return struct.pack("<d", float(v))
    # VAR_STRING / STRING / BLOB / NEWDECIMAL -> length-encoded text bytes
    return lenenc_str(str(v))


def binary_row(values, field_types):
    """A COM_STMT_EXECUTE binary row: 0x00 header + null bitmap (+2 offset) + values."""
    n = len(values)
    nb = (n + 9) >> 3
    bitmap = bytearray(nb)
    body = bytearray()
    for i, (v, t) in enumerate(zip(values, field_types)):
        if v is None:
            bitmap[(i + 2) >> 3] |= 1 << ((i + 2) & 7)
            continue
        body += binary_value(v, t)
    return b"\x00" + bytes(bitmap) + bytes(body)


# ---------------------------------------------------------------------------
# Higher-level response builders (return a full multi-packet byte blob)
# ---------------------------------------------------------------------------
def _resultset(columns, rows, row_encoder, start_seq=1, last=True):
    """columns: list of (name, field_type[, charset]); rows: list of value tuples."""
    out = pkt(start_seq, lenenc_int(len(columns)))
    seq = start_seq + 1
    types = []
    for col in columns:
        name, ftype = col[0], col[1]
        charset = col[2] if len(col) > 2 else (63 if ftype in (MYSQL_TYPE_BLOB,) else 33)
        length = col[3] if len(col) > 3 else 255
        types.append(ftype)
        out += pkt(seq, column_def(name, ftype, charset=charset, length=length))
        seq += 1
    out += pkt(seq, eof_body())                       # EOF after column defs
    seq += 1
    status = _STATUS_AUTOCOMMIT if last else (_STATUS_AUTOCOMMIT | 0x0008)  # MORE_RESULTS
    for r in rows:
        out += pkt(seq, row_encoder(r, types))
        seq += 1
    out += pkt(seq, eof_body(status=status))          # terminating EOF
    return out, seq + 1


def text_resultset(columns, rows, start_seq=1, last=True):
    return _resultset(columns, rows,
                      lambda r, types: b"".join(text_value(v) for v in r),
                      start_seq=start_seq, last=last)[0]


def binary_resultset(columns, rows, start_seq=1, last=True):
    return _resultset(columns, rows,
                      lambda r, types: binary_row(r, types),
                      start_seq=start_seq, last=last)[0]


def text_multi_resultset(sets, start_seq=1):
    """Concatenate several text result sets with continuous packet sequence ids;
    all but the last carry MORE_RESULTS_EXIST so nextset() must advance.
    sets: list of (columns, rows)."""
    out = b""
    seq = start_seq
    last_idx = len(sets) - 1
    for idx, (cols, rows) in enumerate(sets):
        blob, seq = _resultset(cols, rows,
                               lambda r, types: b"".join(text_value(v) for v in r),
                               start_seq=seq, last=(idx == last_idx))
        out += blob
    return out


def ok(affected_rows=0, last_insert_id=0, warnings=0, start_seq=1, more_results=False):
    status = _STATUS_AUTOCOMMIT | (0x0008 if more_results else 0)
    return pkt(start_seq, ok_body(affected_rows, last_insert_id, status, warnings))


def error(errno=1064, sqlstate="42000", message="fake error", start_seq=1):
    return pkt(start_seq, err_body(errno, sqlstate, message))


def prepare_ok(stmt_id=1, columns=None, num_params=0, param_types=None, start_seq=1):
    """COM_STMT_PREPARE response: head + (param defs + EOF) + (col defs + EOF)."""
    columns = columns or []
    num_cols = len(columns)
    head = b"\x00" + struct.pack("<IHHBH", stmt_id, num_cols, num_params, 0, 0)
    out = pkt(start_seq, head)
    seq = start_seq + 1
    if num_params > 0:
        for i in range(num_params):
            t = (param_types[i] if param_types else MYSQL_TYPE_VAR_STRING)
            out += pkt(seq, column_def("?", t))
            seq += 1
        out += pkt(seq, eof_body())
        seq += 1
    if num_cols > 0:
        for col in columns:
            name, ftype = col[0], col[1]
            charset = col[2] if len(col) > 2 else 33
            out += pkt(seq, column_def(name, ftype, charset=charset))
            seq += 1
        out += pkt(seq, eof_body())
        seq += 1
    return out


# ---------------------------------------------------------------------------
# Handshake
# ---------------------------------------------------------------------------
def handshake_greeting(extended_caps=0):
    """Protocol-10 HandshakeV10 the fake server sends (seq 0).

    extended_caps: MariaDB extended capability bits (32..63), shifted down to a
    32-bit value (i.e. pass MARIADB_CLIENT_BULK_UNIT_RESULTS to enable bulk).
    Advertised only when non-zero; otherwise the MariaDB extended field is the
    standard reserved zeros (which is also a valid MariaDB handshake)."""
    caps = CLIENT_PROTOCOL_41 | CLIENT_SECURE_CONNECTION | CLIENT_PLUGIN_AUTH
    body = b"\x0a"                                  # protocol version 10
    body += b"11.4.0-MariaDB-fake\x00"              # server version (MUST contain
    #   "MariaDB"/"-maria-" so libmariadb's mariadb_connection() is true and it
    #   reads the MariaDB extended-capability dword — e.g. BULK_OPERATIONS)
    body += struct.pack("<I", 1)                    # thread id
    body += b"\x01\x02\x03\x04\x05\x06\x07\x08"     # auth-plugin-data part 1 (8)
    body += b"\x00"                                 # filler
    body += struct.pack("<H", caps & 0xFFFF)        # capability flags (lower 16)
    body += b"\x21"                                 # charset (utf8_general_ci)
    body += struct.pack("<H", _STATUS_AUTOCOMMIT)   # status flags
    body += struct.pack("<H", (caps >> 16) & 0xFFFF)  # capability flags (upper 16)
    body += b"\x15"                                 # auth-plugin-data length = 21 (MUST)
    # The 10 reserved bytes are split by MariaDB into 6 reserved + a 4-byte
    # extended-capabilities dword (read at base_client _parse_handshake after
    # skipping 6 reserved). The MYSQL capability bit (0x1) is left clear so the
    # client treats us as MariaDB and honors the extended caps.
    body += b"\x00" * 6                              # reserved (6)
    body += struct.pack("<I", extended_caps & 0xFFFFFFFF)  # MariaDB extended caps (4)
    body += b"\x09\x0a\x0b\x0c\x0d\x0e\x0f\x10\x11\x12\x13\x14\x00"  # auth part 2 (12+NUL)
    body += b"mysql_native_password\x00"            # auth plugin name
    return pkt(0, body)


# ---------------------------------------------------------------------------
# Packet reading
# ---------------------------------------------------------------------------
def _recv_exact(conn, n):
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def recv_one_packet(conn):
    """Read one full protocol packet; returns (seq, payload) or (None, None)."""
    header = _recv_exact(conn, 4)
    if header is None:
        return None, None
    length = header[0] | (header[1] << 8) | (header[2] << 16)
    seq = header[3]
    payload = _recv_exact(conn, length) if length else b""
    if payload is None:
        return None, None
    return seq, payload


# ---------------------------------------------------------------------------
# Server + scripted handler
# ---------------------------------------------------------------------------
def send_chunked(conn, data, chunk_size=1, delay=0.002):
    """Send data in small chunks with a delay between them, so the peer's
    non-blocking reads see only partial data. This forces async"""
    for i in range(0, len(data), chunk_size):
        conn.sendall(data[i:i + chunk_size])
        if i + chunk_size < len(data):
            time.sleep(delay)


def scripted_handler(on_query=None, on_prepare=None, on_execute=None, on_bulk=None,
                     extended_caps=0, slow=False, chunk_size=1, chunk_delay=0.002):
    """Build a connection handler that performs the handshake then dispatches
    each client command to the matching callback. A callback receives the
    request payload (bytes) and returns the response byte blob (with packet
    sequence ids starting at 1). Unhandled/None commands get a default OK, so
    connect-time setup queries (SET autocommit / SET NAMES) don't desync.

    With slow=True, COMMAND responses are dripped in chunk_size-byte chunks
    (chunk_delay seconds apart) to exercise the async code paths."""
    def send_response(conn, data):
        if slow:
            send_chunked(conn, data, chunk_size, chunk_delay)
        else:
            conn.sendall(data)

    def handler(conn):
        conn.sendall(handshake_greeting(extended_caps=extended_caps))
        recv_one_packet(conn)                       # client handshake response (discard)
        conn.sendall(ok(start_seq=2))               # accept auth
        while True:
            seq, payload = recv_one_packet(conn)
            if payload is None or not payload:
                return
            com = payload[0]
            if com == COM_QUIT:
                return
            cb = {COM_QUERY: on_query, COM_STMT_PREPARE: on_prepare,
                  COM_STMT_EXECUTE: on_execute, COM_STMT_BULK_EXECUTE: on_bulk}.get(com)
            if cb is None:
                send_response(conn, ok(start_seq=1))    # default: OK
            else:
                send_response(conn, cb(payload))
    return handler


def query_text(payload):
    """Extract the SQL string from a COM_QUERY payload."""
    return payload[1:].decode("utf-8", "replace")


class FakeServer:
    """One-shot TCP fake server on a daemon thread; serves a single connection."""

    def __init__(self, handler):
        self._handler = handler
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(1)
        self.port = self._srv.getsockname()[1]
        self._thread = None
        self.error = None

    def _serve(self):
        try:
            self._srv.settimeout(10)
            conn, _ = self._srv.accept()
            try:
                conn.settimeout(10)
                self._handler(conn)
            finally:
                try:
                    conn.close()
                except OSError:
                    pass
        except Exception as e:           # surface handler errors to the test
            self.error = e
        finally:
            try:
                self._srv.close()
            except OSError:
                pass

    def __enter__(self):
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        if self._thread is not None:
            self._thread.join(timeout=5)
        return False


def fake_conf(port, **extra):
    """Connection kwargs targeting the fake server: plaintext, blind auth."""
    c = dict(user="u", password="p", host="127.0.0.1", port=port,
             ssl=False, connect_timeout=5)
    c.update(extra)
    return c

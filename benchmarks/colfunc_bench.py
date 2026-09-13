"""Row-decoder layout comparison quoted in docs/benchmarks.md (async section).

Ours (inline type dispatch, no per-result-set setup) vs asyncmy-style (a
converter tuple built once per result set, one call per field) on identical
text-protocol row buffers captured from the pure-Python driver.

    taskset -c 4 python colfunc_bench.py      # needs the seq_1_to_N sequence engine
"""
import os, time, decimal, datetime
os.environ["MARIADB_PYTHON_CONNECTOR"] = "python"
import mariadb
from mariadb.impl.client.base_client import BaseClient
from mariadb.impl.client import base_client as bc
from mariadb_shared.constants import FIELD_TYPE

CFG = dict(host=os.environ.get("TEST_DB_HOST", "localhost"), port=int(os.environ.get("TEST_DB_PORT", 3306)),
           user=os.environ.get("TEST_DB_USER", "root"), password=os.environ.get("TEST_DB_PASSWORD", ""),
           database=os.environ.get("TEST_DB_DATABASE", "test"))
if os.environ.get("TEST_DB_UNIX_SOCKET"):
    CFG["unix_socket"] = os.environ["TEST_DB_UNIX_SOCKET"]
MIXED = ("SELECT seq, CONCAT('name', seq), NOW(), CAST(1234.56 AS DECIMAL(10,2)), 3.14e0, CURDATE(), "
         "seq*1000000, REPEAT('x', 20), CURTIME(), seq+1 FROM seq_1_to_{n}")
SHAPES = {"1 row x 1 int (SELECT 1)": "SELECT 1",
          "1 row x 10 mixed": MIXED.format(n=1),
          "1000 rows x 1 int": "SELECT seq FROM seq_1_to_1000",
          "1000 rows x 10 mixed": MIXED.format(n=1000)}

captured = {}
orig = BaseClient._parse_text_rows
def cap(self, buf, pos, end, columns, config, num_cols, rows, thr, single_length=0):
    # keep only what this call consumed: the unconsumed tail is presented again next call
    r = orig(self, buf, pos, end, columns, config, num_cols, rows, thr, single_length)
    captured.setdefault("calls", []).append((bytes(buf[pos:r[0]]), columns, config, num_cols, thr))
    return r
BaseClient._parse_text_rows = cap
conn = mariadb.connect(**CFG); cur = conn.cursor()
cases = {}
for name, sql in SHAPES.items():
    captured.clear(); cur.execute(sql); rows = cur.fetchall()
    calls = captured["calls"]
    buf = b"".join(c[0] for c in calls); _, columns, config, n, thr = calls[0]
    cases[name] = ((buf, columns, config, n, thr), rows)
BaseClient._parse_text_rows = orig
client = conn._client if hasattr(conn, "_client") else conn.client

# ---- asyncmy-style variant: per-result-set converter tuple, one call per field ----
_int, _float, _bytes = int, float, bytes
_Decimal = decimal.Decimal
_dt_iso = datetime.datetime.fromisoformat; _d_iso = datetime.date.fromisoformat; _td = datetime.timedelta
def conv_str(v): return v.decode('utf-8', 'ignore')
def conv_dec(v): return _Decimal(v.decode('ascii'))
def conv_dt(v): return _dt_iso(v.decode('ascii')) if len(v) >= 19 else None
def conv_date(v): return _d_iso(v.decode('ascii')) if len(v) == 10 else None
def conv_time(v):
    negative = v[0] == 45; parts = (v[1:] if negative else v).split(b':')
    if len(parts) != 3: return None
    seconds, _, fraction = parts[2].partition(b'.')
    td = _td(0, _int(parts[0]) * 3600 + _int(parts[1]) * 60 + _int(seconds), _int(fraction.ljust(6, b'0')) if fraction else 0)
    return -td if negative else td
CONV = {}
for t in bc._TEXT_INT_TYPES: CONV[t] = _int
for t in bc._TEXT_FLOAT_TYPES: CONV[t] = _float
for t in bc._TEXT_DECIMAL_TYPES: CONV[t] = conv_dec
for t in bc._TEXT_DATETIME_TYPES: CONV[t] = conv_dt
for t in bc._TEXT_DATE_TYPES: CONV[t] = conv_date
CONV[FIELD_TYPE.TIME] = conv_time
def build_converters(columns, num_cols):
    """asyncmy's _get_descriptions() equivalent: one converter per column."""
    types, charsets, special = columns.types, columns.charsets, columns.special_formats
    out = [None] * num_cols
    for i in range(num_cols):
        t = types[i]
        if t in bc._TEXT_STRING_TYPES:
            out[i] = conv_str if (charsets[i] != 63 or special[i]) else _bytes
        else:
            out[i] = CONV.get(t, conv_str)
    return tuple(out)
_unpack_I, _unpack_H, _unpack_Q = bc._unpack_I, bc._unpack_H, bc._unpack_Q
def parse_rows_colfunc(buf, pos, end, converters, num_cols, rows, thr):
    rows_append = rows.append
    while end - pos >= 4:
        hdr = _unpack_I(buf, pos)[0]; length = hdr & 0xFFFFFF; start = pos + 4
        if length == 0xFFFFFF or length == 0: return pos, False
        stop = start + length
        if stop > end: break
        first = buf[start]
        if first >= 0xFE and (first == 0xFF or length < thr): return pos, False
        row_values = [None] * num_cols; pos = start
        for i in range(num_cols):
            length_byte = buf[pos]
            if length_byte < 0xFB: length = length_byte; vstart = pos + 1
            elif length_byte == 0xFB: pos += 1; continue
            elif length_byte == 0xFC: length = _unpack_H(buf, pos + 1)[0]; vstart = pos + 3
            elif length_byte == 0xFD: length = _unpack_I(buf, pos + 1)[0] & 0xFFFFFF; vstart = pos + 4
            else: length = _unpack_Q(buf, pos + 1)[0]; vstart = pos + 9
            pos = vstart + length
            row_values[i] = converters[i](buf[vstart:pos])
        rows_append(tuple(row_values)); pos = stop
    return pos, True

def best(fn, n_repeat, n_inner):
    for _ in range(50): fn()          # adaptive-interpreter warm-up
    b = 1e9
    for _ in range(n_repeat):
        t0 = time.perf_counter_ns()
        for _ in range(n_inner): fn()
        b = min(b, (time.perf_counter_ns() - t0) / n_inner)
    return b

print(f"{'shape':28s} {'ours':>10s} {'colfunc':>10s} {'delta':>8s}   (per result set, incl. per-result-set setup)")
for name, ((buf, columns, config, n, thr), expected) in cases.items():
    ba = bytearray(buf)
    def ours():
        rows = []; client._parse_text_rows(ba, 0, len(ba), columns, config, n, rows, thr); return rows
    def colfunc():
        convs = build_converters(columns, n)      # per-result-set setup (asyncmy does this per query)
        rows = []; parse_rows_colfunc(ba, 0, len(ba), convs, n, rows, thr); return rows
    assert ours() == expected == colfunc(), name
    inner = 2000 if len(expected) == 1 else 5
    a = best(ours, 15, inner); c = best(colfunc, 15, inner)
    unit = "ns" if a < 1e5 else "us"; f = 1 if unit == "ns" else 1e-3
    print(f"{name:28s} {a*f:10.0f} {c*f:10.0f} {100*(c-a)/a:+7.1f}%  {unit}")
conn.close()

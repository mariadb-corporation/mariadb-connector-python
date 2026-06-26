# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab
"""
Option-file (my.cnf / my.ini) reader for the pure-Python client.

This mirrors MariaDB Connector/C's ``ma_default.c`` so that the ``default_file``
and ``default_group`` connection parameters behave identically in the pure-Python
and C implementations:

  * **File selection** - a non-empty ``default_file`` is read on its own;
    otherwise the system search path (``/etc``, ``/etc/mysql``, then
    ``$MARIADB_HOME`` or ``$MYSQL_HOME``) is scanned for ``my.cnf``, followed by
    ``~/.my.cnf``.
  * **Groups** - ``[client]``, ``[client-server]`` and ``[client-mariadb]`` are
    always read, plus the caller-supplied ``default_group``. Group and option
    names are matched case-sensitively, as in libmariadb.
  * **Option keys** - taken from libmariadb's ``mariadb_defaults[]`` table; an
    option name is normalised by replacing ``_`` with ``-`` before lookup
    (CONC-395). ``ssl-*`` and ``tls-*`` spellings are both accepted.
  * **Syntax** - ``#``/``;`` comments, ``!include``/``!includedir`` directives
    (recursion capped at 64), surrounding quotes and backslash escapes
    (``\\n \\t \\r \\b \\s \\" \\' \\\\``) are handled the same way.

Only options the pure-Python client can honour are applied; keys that exist in
libmariadb but have no pure-Python equivalent (e.g. ``default-character-set``,
``debug``, ``plugin-dir``) are parsed and ignored, exactly as an unknown key is.
"""
import os
import sys
from typing import Dict, List, Tuple

# A value parsed from an option file: str/int/bool, or None when an option is
# explicitly unset. This is exactly what ``_convert`` produces.
_OptValue = str | int | bool | None

# libmariadb reads ``.cnf`` everywhere and additionally ``.ini`` on Windows.
_INI_EXTS: Tuple[str, ...] = ("ini", "cnf") if sys.platform == "win32" else ("cnf",)

# Groups libmariadb always reads, in addition to the caller's default_group.
_STD_GROUPS: Tuple[str, ...] = ("client", "client-server", "client-mariadb")

_RECURSION_LIMIT = 64

# Recognised option keys -> (Configuration attribute, kind). Keys use the
# normalised dash form (libmariadb replaces '_' with '-' before the lookup).
# This is the subset of libmariadb's mariadb_defaults[] that the pure-Python
# client can apply; recognised-but-unsupported keys are deliberately absent and
# therefore ignored, just like unknown keys.
_OPT_MAP: Dict[str, Tuple[str, str]] = {
    "host": ("host", "str"),
    "servername": ("host", "str"),
    "port": ("port", "int"),
    "socket": ("unix_socket", "str"),
    "user": ("user", "str"),
    "password": ("password", "str"),
    "passwd": ("password", "str"),
    "database": ("database", "str"),
    "db": ("database", "str"),
    "protocol": ("protocol", "int"),
    "connect-timeout": ("connect_timeout", "int"),
    "timeout": ("connect_timeout", "int"),
    "compress": ("compress", "bool"),
    "local-infile": ("local_infile", "bool"),
    "init-command": ("init_command", "str"),
    "max-allowed-packet": ("max_allowed_packet", "int"),
    # TLS / SSL - libmariadb accepts both ssl-* and tls-* spellings.
    "ssl-key": ("ssl_key", "str"), "tls-key": ("ssl_key", "str"),
    "ssl-cert": ("ssl_cert", "str"), "tls-cert": ("ssl_cert", "str"),
    "ssl-ca": ("ssl_ca", "str"), "tls-ca": ("ssl_ca", "str"),
    "ssl-capath": ("ssl_capath", "str"), "tls-capath": ("ssl_capath", "str"),
    "ssl-crl": ("ssl_crl", "str"), "tls-crl": ("ssl_crl", "str"),
    "ssl-crlpath": ("ssl_crlpath", "str"), "tls-crlpath": ("ssl_crlpath", "str"),
    "ssl-cipher": ("ssl_cipher", "str"), "tls-cipher": ("ssl_cipher", "str"),
    "ssl-verify-server-cert": ("ssl_verify_cert", "bool"),
    "tls-verify-peer": ("ssl_verify_cert", "bool"),
    "ssl-enforce": ("ssl", "bool"), "tls-enforce": ("ssl", "bool"),
    "tls-version": ("tls_version", "str"),
}

_ESCAPES = {
    "n": "\n", "t": "\t", "r": "\r", "b": "\b", "s": " ",
    '"': '"', "'": "'", "\\": "\\",
}


def _atoi(value: str | None) -> int:
    """Parse a leading optional sign and digits, returning 0 otherwise (C ``atoi``)."""
    if not value:
        return 0
    s = value.strip()
    i = 1 if s[:1] in "+-" else 0
    j = i
    while j < len(s) and s[j].isdigit():
        j += 1
    if j == i:
        return 0
    return int(s[:j])


def _convert(kind: str, value: str | None) -> _OptValue:
    if kind == "str":
        # MARIADB_OPTION_STR: an empty value unsets the option.
        return value if value else None
    if kind == "bool":
        # MARIADB_OPTION_BOOL: atoi(value); a bare option (no value) is 0/False.
        return bool(_atoi(value))
    return _atoi(value)  # int / sizet


def _strip_and_unescape(raw: str) -> str:
    """Apply libmariadb's value handling: trim, de-quote, then process escapes."""
    value = raw.strip()
    # Strip a leading quote, and a trailing quote only if one is also present.
    if value[:1] in ('"', "'"):
        if len(value) >= 2 and value[-1] in ('"', "'"):
            value = value[1:-1]
        else:
            value = value[1:]
    out: List[str] = []
    i, n = 0, len(value)
    while i < n:
        ch = value[i]
        if ch == "\\" and i != n - 1:  # a trailing backslash is kept literally
            i += 1
            nxt = value[i]
            mapped = _ESCAPES.get(nxt)
            if mapped is None:  # unknown escape: keep the backslash and the char
                out.append("\\")
                out.append(nxt)
            else:
                out.append(mapped)
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _store(out: Dict[str, _OptValue], key: str, value: str | None) -> None:
    entry = _OPT_MAP.get(key.replace("_", "-"))  # CONC-395: '_' -> '-'
    if entry is None:
        return
    field, kind = entry
    out[field] = _convert(kind, value)


def _is_config_file(path: str) -> bool:
    if not os.access(path, os.R_OK):
        return False
    return any(path.endswith("." + ext) for ext in _INI_EXTS)


def _read_includedir(directory: str, group: str | None,
                     recursion: int, out: Dict[str, _OptValue]) -> None:
    try:
        names = os.listdir(directory)
    except OSError:
        return
    found = [n for n in names if _is_config_file(os.path.join(directory, n))]
    found.sort()  # libmariadb reads the directory entries in sorted order
    for name in found:
        _read_file(os.path.join(directory, name), group, recursion + 1, out)


def _read_file(path: str, group: str | None,
               recursion: int, out: Dict[str, _OptValue]) -> None:
    if recursion >= _RECURSION_LIMIT:
        return
    groups = set(_STD_GROUPS)
    if group:
        groups.add(group)
    try:
        handle = open(path, "r", encoding="utf-8", errors="replace")
    except OSError:
        return

    read_values = False
    found_group = False
    is_escaped = False
    with handle:
        for line in handle:
            line = line.lstrip()
            # A line that is just a quote toggles libmariadb's (otherwise unused)
            # quote state and is skipped.
            if not is_escaped and line[:1] in ('"', "'"):
                continue
            if line[:1] == "!":  # !include / !includedir
                parts = line[1:].strip().split(None, 1)
                if len(parts) == 2:
                    directive, target = parts[0], parts[1].strip()
                    if directive == "includedir":
                        _read_includedir(target, group, recursion, out)
                    elif directive == "include":
                        _read_file(target, group, recursion + 1, out)
                continue
            if line[:1] in ("#", ";") or not line.strip():
                continue
            is_escaped = line[:1] == "\\"
            if line[:1] == "[":  # group header
                end = line.find("]")
                if end < 0:
                    return  # malformed group line
                found_group = True
                read_values = line[1:end].strip() in groups
                continue
            if not found_group:
                return  # option before any group: malformed
            if not read_values:
                continue
            if "=" not in line:
                _store(out, line.strip(), None)  # bare option
            else:
                key, _sep, raw = line.partition("=")
                _store(out, key.strip(), _strip_and_unescape(raw))


def _config_dirs() -> List[str]:
    dirs: List[str] = []

    def add(directory: str | None) -> None:
        if directory and directory not in dirs:
            dirs.append(directory)

    if sys.platform == "win32":
        add(os.environ.get("SystemRoot") or os.environ.get("WINDIR"))
        add("C:")
    else:
        add("/etc")
        add("/etc/mysql")
    add(os.environ.get("MARIADB_HOME") or os.environ.get("MYSQL_HOME"))
    return dirs


def read_option_files(default_file: str | None,
                      default_group: str | None) -> Dict[str, _OptValue]:
    """
    Read option file(s) and return a ``{Configuration attribute: value}`` mapping.

    Values are already typed (str/int/bool). When multiple files or groups set the
    same option, the last one read wins - the same ordering libmariadb uses.
    """
    out: Dict[str, _OptValue] = {}

    if default_file:  # a non-empty path is read on its own
        _read_file(default_file, default_group, 0, out)
        return out

    for directory in _config_dirs():
        for ext in _INI_EXTS:
            path = os.path.join(directory, "my." + ext)
            if os.access(path, os.R_OK):
                _read_file(path, default_group, 0, out)

    if sys.platform != "win32":
        home = os.environ.get("HOME")
        if home:
            for ext in _INI_EXTS:
                path = os.path.join(home, ".my." + ext)
                if os.access(path, os.R_OK):
                    _read_file(path, default_group, 0, out)
    return out

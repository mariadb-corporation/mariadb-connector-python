# SPDX-License-Identifier: LGPL-2.1-or-later
"""
Unit tests for option-file (my.cnf) handling in the pure-Python client.

These mirror MariaDB Connector/C's ma_default.c behaviour: which groups are read,
the option-name -> parameter mapping, '_' -> '-' normalisation, quote/escape
handling, !include/!includedir, and that explicit kwargs override file values.
"""
import os
import sys
import tempfile
import textwrap

import pytest

# The ~/.my.cnf home-directory scan is Unix-only, mirroring libmariadb's
# ma_default.c (the HOME lookup is wrapped in `#ifndef _WIN32`).
skip_on_windows = pytest.mark.skipif(
    sys.platform == "win32",
    reason="~/.my.cnf is only read on non-Windows platforms (see ma_default.c)",
)

from mariadb.impl.option_file import read_option_files
from mariadb.impl.configuration import Configuration


@pytest.fixture
def cnf(tmp_path):
    """Write a my.cnf and return (path, include_dir)."""
    incdir = tmp_path / "conf.d"
    incdir.mkdir()
    (incdir / "z.cnf").write_text("[client]\nmax-allowed-packet = 99\n")
    path = tmp_path / "my.cnf"
    path.write_text(textwrap.dedent(f"""\
        # comment
        ; comment
        [mysqld]
        user = should_not_be_read
        [client]
        user = alice
        passwd = "sec\\tret"
        port = 3307
        servername = db.example
        socket = /tmp/s.sock
        ssl_ca = /etc/ca.pem
        tls-cipher = 'AES'
        ssl-verify-server-cert = 0
        compress
        local-infile = 1
        [myapp]
        db = appdb
        host = apphost
        !includedir {incdir}
        """))
    return str(path), str(incdir)


def test_client_group_mapping(cnf):
    path, _ = cnf
    opts = read_option_files(path, None)
    assert opts["user"] == "alice"
    assert opts["port"] == 3307
    assert opts["host"] == "db.example"          # servername alias
    assert opts["unix_socket"] == "/tmp/s.sock"  # socket
    assert opts["ssl_ca"] == "/etc/ca.pem"       # ssl_ca normalised to ssl-ca
    assert opts["ssl_cipher"] == "AES"           # tls-cipher alias, quotes stripped
    assert opts["ssl_verify_cert"] is False
    assert opts["local_infile"] is True


def test_mysqld_group_not_read(cnf):
    path, _ = cnf
    # 'user' must come from [client], never the [mysqld] section
    assert read_option_files(path, None)["user"] == "alice"


def test_escape_sequence(cnf):
    path, _ = cnf
    assert read_option_files(path, None)["password"] == "sec\tret"


def test_bare_bool_is_false(cnf):
    # libmariadb: a bare boolean option (no value) is atoi(NULL) == 0
    path, _ = cnf
    assert read_option_files(path, None)["compress"] is False


def test_default_group_scoping(cnf):
    path, _ = cnf
    # [myapp] keys only when default_group asks for it
    assert "database" not in read_option_files(path, None)
    opts = read_option_files(path, "myapp")
    assert opts["database"] == "appdb"
    assert opts["host"] == "apphost"   # [myapp] host overrides [client] servername


def test_includedir(cnf):
    path, _ = cnf
    assert read_option_files(path, None)["max_allowed_packet"] == 99


def test_unknown_keys_ignored(tmp_path):
    path = tmp_path / "bad.cnf"
    path.write_text("[client]\ndebug = x\nplugin-dir = /p\nbogus = 1\nuser = z\n")
    assert read_option_files(str(path), None) == {"user": "z"}


def test_from_dict_applies_file(cnf):
    path, _ = cnf
    cfg = Configuration.from_dict({"default_file": path, "default_group": "myapp"})
    assert cfg.user == "alice"
    assert cfg.database == "appdb"
    assert cfg.ssl_verify_cert is False
    assert cfg.default_file == path


def test_explicit_kwargs_override_file(cnf):
    path, _ = cnf
    cfg = Configuration.from_dict(
        {"default_file": path, "default_group": "myapp", "user": "explicit", "port": 3399}
    )
    assert cfg.user == "explicit"   # explicit overrides file
    assert cfg.port == 3399
    assert cfg.host == "apphost"    # untouched file value survives


def test_no_default_params_means_no_file_read(tmp_path, monkeypatch):
    # Without default_file/default_group, no option file is consulted at all.
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".my.cnf").write_text("[client]\nuser = fromhome\n")
    cfg = Configuration.from_dict({"host": "h"})
    assert cfg.user is None  # default, .my.cnf NOT read


def test_missing_file_is_silent(tmp_path):
    missing = str(tmp_path / "nope.cnf")
    assert read_option_files(missing, None) == {}


# --- None vs "" vs path vs group trigger, mirroring libmariadb exactly --------

def test_default_file_none_reads_nothing(tmp_path, monkeypatch):
    # default_file=None (explicit) behaves like absent: NULL my_cnf_file, gate
    # false, nothing read - not a search-path scan.
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".my.cnf").write_text("[client]\nuser = fromhome\n")
    assert Configuration.from_dict({"default_file": None}).user is None


@skip_on_windows
def test_empty_default_file_scans_search_path(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".my.cnf").write_text("[client]\nuser = fromhome\n")
    assert Configuration.from_dict({"default_file": ""}).user == "fromhome"


def test_specific_file_skips_search_path(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".my.cnf").write_text("[client]\nuser = fromhome\n")
    explicit = tmp_path / "explicit.cnf"
    explicit.write_text("[client]\nuser = fromfile\n")
    assert Configuration.from_dict({"default_file": str(explicit)}).user == "fromfile"


@skip_on_windows
def test_default_group_alone_scans_search_path(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".my.cnf").write_text("[client]\nuser = fromhome\n")
    assert Configuration.from_dict({"default_group": "client"}).user == "fromhome"

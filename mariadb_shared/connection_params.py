# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab

"""
Typed connection parameters.

``ConnectionParams`` is the type-checking contract of the keyword arguments
accepted by ``mariadb.connect()``, ``mariadb.asyncConnect()``, the pool
factories and the connection classes of every implementation. Used as
``**kwargs: Unpack[ConnectionParams]``, it gives callers completion and
checking of each parameter name and type without changing the keyword API
that DB-API 2.0 and the ORMs rely on.

It is deliberately the union of what the implementations accept: the fields
of the pure-Python ``Configuration`` and the keywords of the C extension.
``ConnectParams`` adds the pool options ``connect()`` alone still routes for
1.1 compatibility (the pool factories name those as regular parameters, and
``asyncConnect()`` rejects them). ``tests/unit/test_connection_params.py``
keeps them in sync with their sources.
"""

from typing import Any, Callable, Dict, TypedDict


class ConnectionParams(TypedDict, total=False):
    """Keyword arguments of connect() / asyncConnect(); every key is optional."""

    # --- server / credentials -------------------------------------------------
    dsn: str
    host: str
    port: int
    user: str | None
    username: str | None  # alias of user
    password: str | None
    passwd: str | None  # alias of password
    database: str | None
    db: str | None  # alias of database
    unix_socket: str | None
    protocol: int  # 0=DEFAULT, 1=TCP, 2=SOCKET (mysql_protocol_type)
    default_file: str | None
    default_group: str | None
    plugin_dir: str | None
    init_command: str | None

    # --- timeouts / transport -------------------------------------------------
    connect_timeout: float
    read_timeout: int
    write_timeout: int
    socket_timeout: float | None
    compress: bool
    local_infile: bool | None
    reconnect: bool
    client_flag: int
    max_allowed_packet: int
    max_allowed_columns: int
    query_timeout: int

    # --- TLS ------------------------------------------------------------------
    ssl: bool | Dict[str, Any]  # a dict is expanded into the ssl_* parameters
    ssl_key: str | None
    ssl_ca: str | None
    ssl_cert: str | None
    ssl_crl: str | None
    ssl_cipher: str | None
    ssl_capath: str | None
    ssl_crlpath: str | None
    ssl_verify_cert: bool
    tls_version: str | None
    tls_fp: str | None
    tls_fp_list: str | None

    # --- session / results ----------------------------------------------------
    autocommit: bool
    read_only: bool
    binary: bool
    named_tuple: bool
    dictionary: bool
    native_object: bool
    converter: Dict[int, Callable[[Any], Any]] | None
    cache_prep_stmts: bool
    prep_stmt_cache_size: int
    pipeline: bool
    status_callback: Callable[..., Any] | None

    # --- 1.1 spellings of pool options, also accepted by the pool factories ---
    pool_size: int
    pool_reset_connection: bool
    pool_validation_interval: float


class ConnectParams(ConnectionParams, total=False):
    """Keyword arguments of connect(): the connection parameters plus the pool
    options it still accepts for 1.1 compatibility (a named pool is created,
    or looked up, and a connection borrowed from it)."""

    pool_name: str
    min_size: int
    max_size: int
    max_idle_time: float
    max_lifetime: float
    acquire_timeout: float
    ping_threshold: float
    enable_health_check: bool
    reset_connection: bool

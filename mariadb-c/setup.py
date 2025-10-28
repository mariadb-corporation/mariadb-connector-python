#!/usr/bin/env python
"""
Setup script for mariadb-connector-python.
All metadata is now in pyproject.toml (PEP 621).
This file only handles dynamic C extension configuration.
"""

import os
import sys
from configparser import ConfigParser
from setuptools import setup, Extension

# Add current directory to path to import mariadb_posix/mariadb_windows
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if os.name == "posix":
    from mariadb_posix import get_config
if os.name == "nt":
    from mariadb_windows import get_config  # noqa: F811

define_macros = []

# read settings from site.cfg
c = ConfigParser()
c.read(['site.cfg'])
options = dict(c.items('cc_options'))

cfg = get_config(options)

PY_MARIADB_AUTHORS = "Georg Richter"

PY_MARIADB_MAJOR_VERSION = 1
PY_MARIADB_MINOR_VERSION = 1
PY_MARIADB_PATCH_VERSION = 15
PY_MARIADB_PRE_RELEASE_SEGMENT = None
PY_MARIADB_PRE_RELEASE_NR = 0
PY_MARIADB_POST_RELEASE_SEGMENT = None
PY_MARIADB_POST_RELEASE_NR = 0

PY_MARIADB_VERSION = "%s.%s.%s" % (PY_MARIADB_MAJOR_VERSION,
                                   PY_MARIADB_MINOR_VERSION,
                                   PY_MARIADB_PATCH_VERSION)

if PY_MARIADB_POST_RELEASE_SEGMENT:
    PY_MARIADB_VERSION += ".%s" % (PY_MARIADB_POST_RELEASE_SEGMENT +
                                   PY_MARIADB_POST_RELEASE_NR)

PY_MARIADB_VERSION_INFO = (PY_MARIADB_MAJOR_VERSION,
                           PY_MARIADB_MINOR_VERSION,
                           PY_MARIADB_PATCH_VERSION)

if PY_MARIADB_PRE_RELEASE_SEGMENT:
    PY_MARIADB_VERSION_INFO = PY_MARIADB_VERSION_INFO + (
                                  PY_MARIADB_PRE_RELEASE_SEGMENT,
                                  PY_MARIADB_PRE_RELEASE_NR)

if PY_MARIADB_POST_RELEASE_SEGMENT:
    PY_MARIADB_VERSION_INFO = PY_MARIADB_VERSION_INFO + (
                                  PY_MARIADB_POST_RELEASE_SEGMENT,
                                  PY_MARIADB_POST_RELEASE_NR)

define_macros.append(("PY_MARIADB_MAJOR_VERSION", PY_MARIADB_MAJOR_VERSION))
define_macros.append(("PY_MARIADB_MINOR_VERSION", PY_MARIADB_MINOR_VERSION))
define_macros.append(("PY_MARIADB_PATCH_VERSION", PY_MARIADB_PATCH_VERSION))
define_macros.append(("PY_MARIADB_PRE_RELEASE_SEGMENT", "\"%s\"" %
                      PY_MARIADB_PRE_RELEASE_SEGMENT))
define_macros.append(("PY_MARIADB_PRE_RELEASE_NR", "\"%s\"" %
                      PY_MARIADB_PRE_RELEASE_NR))
define_macros.append(("PY_MARIADB_POST_RELEASE_SEGMENT", "\"%s\"" %
                      PY_MARIADB_POST_RELEASE_SEGMENT))
define_macros.append(("PY_MARIADB_POST_RELEASE_NR", "\"%s\"" %
                      PY_MARIADB_POST_RELEASE_NR))


# Legacy release_info.py generation removed - now using modern pyproject.toml versioning

# All metadata is now in pyproject.toml (PEP 621)
# setup.py only handles dynamic C extension configuration
setup(
    ext_modules=[
        Extension(
            'mariadb_c._mariadb',
            [
                'mariadb_c/mariadb.c',
                'mariadb_c/mariadb_codecs.c',
                'mariadb_c/mariadb_connection.c',
                'mariadb_c/mariadb_cursor.c',
                'mariadb_c/mariadb_exception.c',
                'mariadb_c/mariadb_parser.c',
            ],
            define_macros=define_macros,
            include_dirs=cfg.includes,
            library_dirs=cfg.lib_dirs,
            libraries=cfg.libs,
            extra_compile_args=cfg.extra_compile_args,
            extra_link_args=cfg.extra_link_args,
            extra_objects=cfg.extra_objects,
        )
    ],
)

#!/usr/bin/env python

import subprocess  # nosec B404
from packaging import version
import sys
import os


class MariaDBConfiguration():
    lib_dirs = []
    libs = []
    version = []
    includes = []
    extra_objects = []
    extra_compile_args = []
    extra_link_args = []


_MARIADB_CONFIG_NOT_FOUND = """mariadb_config not found.

This error typically indicates that MariaDB Connector/C, a dependency which
must be preinstalled, is not found.
If MariaDB Connector/C is not installed, see installation instructions
If MariaDB Connector/C is installed, either set the environment variable
MARIADB_CONFIG or edit the configuration file 'site.cfg' to set the
 'mariadb_config' option to the file location of the mariadb_config utility.
"""


def mariadb_config(config, option):
    try:
        proc = subprocess.run(  # nosec B603
            [config, "--%s" % option],
            stdout=subprocess.PIPE,
            text=True,
        )
    except OSError:
        raise EnvironmentError(_MARIADB_CONFIG_NOT_FOUND)
    data = proc.stdout.strip().split()
    rc = proc.returncode
    if rc:
        data = []
        if rc != 1:
            raise EnvironmentError(_MARIADB_CONFIG_NOT_FOUND)

    return data


def dequote(s):
    if s[0] in "\"'" and s[0] == s[-1]:
        s = s[1:-1]
    return s


def get_config(options):
    required_version = "3.3.1"
    static = options["link_static"]

    try:
        try:
            config_prg = os.environ["MARIADB_CONFIG"]
        except KeyError:
            config_prg = options["mariadb_config"]
        subprocess.call([config_prg, "--cc_version"])  # nosec B603
    except FileNotFoundError:
        # using default from path
        config_prg = "mariadb_config"

    cc_version = mariadb_config(config_prg, "cc_version")
    if version.Version(cc_version[0]) < version.Version(required_version):
        print('MariaDB Connector/Python requires MariaDB Connector/C '
              '>= %s, found version %s' % (required_version, cc_version[0]))
        sys.exit(2)
    cfg = MariaDBConfiguration()
    cfg.version = cc_version[0]

    plugindir = mariadb_config(config_prg, "plugindir")
    libs = mariadb_config(config_prg, "libs")
    extra_libs = mariadb_config(config_prg, "libs_sys")
    cfg.lib_dirs = [dequote(i[2:]) for i in libs if i.startswith("-L")]

    cfg.libs = [dequote(i[2:]) for i in libs if i.startswith("-l")]
    includes = mariadb_config(config_prg, "include")
    mariadb_includes = [dequote(i[2:]) for i in includes if i.startswith("-I")]
    mariadb_includes.extend(["./include"])
    if static.lower() == "on":
        cfg.extra_link_args = ["-u mysql_ps_fetch_functions"]
        cfg.extra_objects = ['{}/lib{}.a'.format(cfg.lib_dirs[0], lib)
                             for lib in ["mariadbclient"]]
        cfg.libs = [dequote(i[2:])
                    for i in extra_libs if i.startswith("-l")]
    cfg.includes = mariadb_includes
    cfg.extra_compile_args = ["-DDEFAULT_PLUGINS_SUBDIR=\"%s\"" % plugindir[0]]
    return cfg

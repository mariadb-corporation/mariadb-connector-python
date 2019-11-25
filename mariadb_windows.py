import os
import platform
import sys

from winreg import *


class MariaDBConfiguration():
    lib_dirs = []
    libs = []
    version = []
    includes = []
    extra_objects = []
    extra_compile_args= []
    extra_link_args= []


def get_config(options):
    required_version = "3.1.0"

    static= options["link_static"];
    mariadb_dir= options["install_dir"]

    cfg = MariaDBConfiguration()
    cfg.includes = [".\\include", options["install_dir"] + "\\include", options["install_dir"] + "\\include\\mysql"]
    cfg.lib_dirs = [options["install_dir"] + "\\lib"]
    cfg.libs = ["ws2_32", "advapi32", "kernel32", "shlwapi", "crypt32"]
    if static:
        cfg.libs.append("mariadbclient")
    else:
        cfg.libs.append("libmariadb")
    cfg.extra_link_args= ["/NODEFAULTLIB:LIBCMT"]
    return cfg

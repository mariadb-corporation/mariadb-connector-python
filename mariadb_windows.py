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


def get_config():
    required_version = "3.1.0"

    try:
        static= os.environ["MARIADB_STATIC"]
    except KeyError:
        static= 0

    try:
        config_prg = os.environ["MARIADB_CC_INSTALL_DIR"]
        cc_version = ["", ""]
        cc_instdir = [config_prg, ""]
        print("using environment configuration " + config_prg)
    except KeyError:

        try:
            local_reg = ConnectRegistry(None, HKEY_LOCAL_MACHINE)
            if platform.architecture()[0] == '32bit':
                connector_key = OpenKey(local_reg,
                                        'SOFTWARE\\MariaDB Corporation\\MariaDB Connector C')
            else:
                connector_key = OpenKey(local_reg,
                                        'SOFTWARE\\MariaDB Corporation\\MariaDB Connector C 64-bit',
                                        access=KEY_READ | KEY_WOW64_64KEY)
            cc_version = QueryValueEx(connector_key, "Version")
            if cc_version[0] < required_version:
                print(
                         "MariaDB Connector/Python requires MariaDB Connector/C >= %s (found version: %s") \
                     % (required_version, cc_version[0])
                sys.exit(2)
            cc_instdir = QueryValueEx(connector_key, "InstallDir")

        except:
            print("Could not find InstallationDir of MariaDB Connector/C. "
                  "Please make sure MariaDB Connector/C is installed or specify the InstallationDir of "
                  "MariaDB Connector/C by setting the environment variable MARIADB_CC_INSTALL_DIR.")
            sys.exit(3)

    cfg = MariaDBConfiguration()
    cfg.version = cc_version[0]
    cfg.includes = [".\\include", cc_instdir[0] + "\\include", cc_instdir[0] + "\\include\\mysql"]
    cfg.lib_dirs = [cc_instdir[0] + "\\lib"]
    cfg.libs = ["ws2_32", "advapi32", "kernel32", "shlwapi", "crypt32"]
    if static:
        cfg.libs.append("mariadbclient")
    else:
        cfg.libs.append("libmariadb")
    cfg.extra_link_args= ["/NODEFAULTLIB:LIBCMT"]
    return cfg

#
# Windows configuration
#

import os
import platform
import sys
from packaging import version

from winreg import ConnectRegistry, OpenKey, QueryValueEx,\
    HKEY_LOCAL_MACHINE, KEY_READ, KEY_WOW64_64KEY


class MariaDBConfiguration():
    lib_dirs = []
    libs = []
    version = []
    includes = []
    extra_objects = []
    extra_compile_args = []
    extra_link_args = []


def get_config(options):
    static = options["link_static"]
    mariadb_dir = options["install_dir"]
    required_version = "3.2.4"

    if not os.path.exists(mariadb_dir):
        try:
            mariadb_dir = os.environ["MARIADB_CC_INSTALL_DIR"]
            cc_version = ["", ""]
            print("using environment configuration " + mariadb_dir)
        except KeyError:

            try:
                local_reg = ConnectRegistry(None, HKEY_LOCAL_MACHINE)
                if platform.architecture()[0] == '32bit':
                    connector_key = OpenKey(local_reg,
                                            'SOFTWARE\\MariaDB Corporation\\'
                                            'MariaDB Connector C')
                else:
                    connector_key = OpenKey(local_reg,
                                            'SOFTWARE\\MariaDB Corporation\\'
                                            'MariaDB Connector C 64-bit',
                                            access=KEY_READ | KEY_WOW64_64KEY)
                cc_version = QueryValueEx(connector_key, "Version")
                if (version.Version(cc_version[0]) <
                        version.Version(required_version)):
                    print("MariaDB Connector/Python requires "
                          "MariaDB Connector/C "
                          ">= %s (found version: %s") \
                          % (required_version, cc_version[0])
                    sys.exit(2)
                mariadb_dir = QueryValueEx(connector_key, "InstallDir")[0]

            except Exception:
                print("Could not find InstallationDir of MariaDB Connector/C. "
                      "Please make sure MariaDB Connector/C is installed or "
                      "specify the InstallationDir of MariaDB Connector/C by "
                      "setting the environment variable "
                      "MARIADB_CC_INSTALL_DIR.")
                sys.exit(3)

    print("Found MariaDB Connector/C in '%s'" % mariadb_dir)
    cfg = MariaDBConfiguration()
    cfg.includes = [".\\include", mariadb_dir + "\\include", mariadb_dir +
                    "\\include\\mysql"]
    cfg.lib_dirs = [mariadb_dir + "\\lib"]
    cfg.libs = ["ws2_32", "advapi32", "kernel32", "shlwapi", "crypt32",
                "secur32", "bcrypt"]
    if static.lower() == "on" or static.lower() == "default":
        cfg.libs.append("mariadbclient")
    else:
        print("dynamic")
    cfg.extra_link_args = ["/NODEFAULTLIB:LIBCMT"]
    cfg.extra_compile_args = ["/MD"]

    f = open("./include/config_win.h", "w")
    f.write("#define DEFAULT_PLUGINS_SUBDIR \"%s\\\\lib\\\\plugin\"" %
            options["install_dir"].replace(""'\\', '\\\\'))
    f.close()
    return cfg

import sys
import os
import string
from winreg import *

class MariaDBConfiguration():
  lib_dirs= ""
  libs= ""
  version= ""
  includes= ""

def get_config():
  required_version="3.1.0"

  try:
    config_prg= os.environ["MARIADB_CC_DIR"]
    cc_version= ["",""]
    cc_instdir= [config_prg, ""]
    print("using environment configuration " + config_prg)
  except KeyError:
    Registry= ConnectRegistry(None, HKEY_LOCAL_MACHINE)
    Key= OpenKey(Registry, "SOFTWARE\MariaDB Corporation\MariaDB Connector C 64-bit")
    if Key:
      cc_version= QueryValueEx(Key, "Version")
      if cc_version[0] < required_version:
        print("MariaDB Connector/Python requires MariaDB Connector/C >= %s (found version: %s") % (required_version, cc_version[0])

        sys.exit(2)
      cc_instdir= QueryValueEx(Key, "InstallDir")
    if cc_instdir is None:
      print("Could not find InstallationDir of MariaDB Connector/C. Please make sure MariaDB Connector/C is installed or specify the InstallationDir of MariaDB Connector/C by setting the environment variable MARIADB_CC_INSTALL_DIR.")
      sys.exit(3)

  
  cfg= MariaDBConfiguration()
  cfg.version= cc_version[0]
  cfg.includes= [".\\include", cc_instdir[0] + "\\include", cc_instdir[0] + "\\include\\mysql"]
  cfg.lib_dirs= [cc_instdir[0] + "\\lib"]
  cfg.libs= ["mariadbclient", "ws2_32", "advapi32",  "kernel32",  "shlwapi", "crypt32"]
  return cfg

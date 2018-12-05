#!/usr/bin/env python

import sys
import os
import string

class MariaDBConfiguration():
  lib_dirs= ""
  libs= ""
  version= ""
  includes= ""


def mariadb_config(config, option):
  from os import popen
  file= popen("%s --%s" % (config, option))
  data= file.read().strip().split()
  rc= file.close()
  if rc:
    if rc/256:
      data= []
    if rc/256 > 1:
      raise EnvironmentError("mariadb_config not found. Hint: you can specify environment variable MARIADB_CONFIG which points to the location of mariadb_config")
  return data


def dequote(s):
  if s[0] in "\"'" and s[0] == s[-1]:
   s = s[1:-1]
  return s

def get_config():
  required_version="3.1.0"

  try:
    config_prg= os.environ["MARIADB_CONFIG"]
  except KeyError:
    print("Please set the environment variable MARIADB_CONFIG which points to the location of the mariadb_config program")
    sys.exit(1)

  cc_version= mariadb_config(config_prg, "cc_version")
  if cc_version[0] < required_version:
    print("MariaDB Connector/C required MariaDB Connector/C >= %s") % (required_version)
    sys.exit(2)
  cfg= MariaDBConfiguration()
  cfg.version= cc_version[0]

  libs= mariadb_config(config_prg, "libs")
  cfg.lib_dirs = [ dequote(i[2:]) for i in libs if i.startswith("-L") ]
  cfg.libs = [ dequote(i[2:]) for i in libs if i.startswith("-l") ]
  includes= mariadb_config(config_prg, "include")
  mariadb_includes = [ dequote(i[2:]) for i in includes if i.startswith("-I") ]
  mariadb_includes.extend(["./include"])
  cfg.includes= mariadb_includes
  return cfg

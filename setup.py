#!/usr/bin/env python

import os
import sys
import subprocess
import string

from distutils.core import setup, Extension
from optparse import OptionParser

def mariadb_config(config, option):
  from os import popen
  if config is None:
    config="mariadb_config"
  file= popen("%s --%s" % (config, option))
  data= file.read().strip().split()
  rc= file.close()
  if rc:
    if rc/256:
      data= []
    if rc/256 > 1:
      raise EnvironmentError("mariadb_config not found")
  return data


def dequote(s):
  if s[0] in "\"'" and s[0] == s[-1]:
   s = s[1:-1]
  return s

parser=OptionParser()
parser.add_option("--mariadb_config", dest="mariadb_config",
                  help="Location of mariadb_config")
required_version="3.1.0"

optlist, args= parser.parse_args()
cc_version= mariadb_config(optlist.mariadb_config, "cc_version")
if cc_version[0] < required_version:
  print("MariaDB Connector/C required MariaDB Connector/C >= %s") % (required_version)
  sys.exit(2)
libs= mariadb_config(optlist.mariadb_config, "libs")
mariadb_lib_dirs = [ dequote(i[2:]) for i in libs if i.startswith("-L") ]
mariadb_libs = [ dequote(i[2:]) for i in libs if i.startswith("-l") ]
includes= mariadb_config(optlist.mariadb_config, "include")
mariadb_includes = [ dequote(i[2:]) for i in includes if i.startswith("-I") ]
mariadb_includes.extend(["./include"])
if optlist.mariadb_config is not None:
  sys.argv.remove("--mariadb_config=%s" % (optlist.mariadb_config))


setup(name='mariadb',
     version='0.9.1',
     description='Python MariaDB extension',
     author='Georg Richter',
     url='http://www.mariadb.com',
     ext_modules=[Extension('mariadb', ['src/mariadb.c', 'src/mariadb_connection.c', 'src/mariadb_exception.c', 'src/mariadb_cursor.c', 'src/mariadb_codecs.c', 'src/mariadb_field.c', 'src/mariadb_dbapitype.c', 'src/mariadb_indicator.c'],
     include_dirs=mariadb_includes,
     library_dirs= mariadb_lib_dirs,
     libraries= mariadb_libs
     )],
     )

#!/usr/bin/env python

import os
import sys
import subprocess

from distutils.core import setup, Extension

def dequote(s):
    if not s:
        raise Exception("Wrong value from mariadb_config")
    if s[0] in "\"'" and s[0] == s[-1]:
        s = s[1:-1]
    return s

def mariadb_config(what):
    from os import popen

    f = popen("%s --%s" % (mariadb_config.path, what))
    data = f.read().strip().split()
    ret = f.close()
    if ret:
        if ret/256:
            data = []
        if ret/256 > 1:
            raise EnvironmentError("%s not found" % (mariadb_config.path,))
    return data

def assure_path_exists(path):
        if not os.path.exists(path):
                os.makedirs(path)

if sys.version_info[0] < 3:
    print("Connector MariaDB/Python requires Python 3.x")
    sys.exit(1)

subprocess.call('git submodule init && git submodule update', shell=True)
assure_path_exists('libmariadb/bld')
subprocess.call('cd libmariadb/bld && cmake .. -DCMAKE_BUILD_TYPE=Release && make -j4', shell=True)

if sys.platform != "win32":

  mariadb_config.path = "./libmariadb/bld/mariadb_config/mariadb_config"
  libs = mariadb_config("libs_sys")
  mariadb_version= mariadb_config("cc_version")
  if mariadb_version[0] < "3.0.6":
    print("Connector MariaDB/Pythin requires MariaDB Connector/C 3.0.6 or newer")
    sys.exit(1)
  mariadb_libraries= [dequote(c[2:])
           for c in libs
            if c.startswith("-l")]
  mariadb_lib_dirs= ['./libmariadb/bld/libmariadb']
  mariadb_includes= ['./libmariadb/include', './libmariadb/bld/include', './libmariadb/bld/include/mysql']
  mariadb_includes.append("./include")

  print(mariadb_includes)

print(mariadb_lib_dirs)
setup(name='mariadb',
      version='0.1',
      description='Python MariaDB extension',
      author='Georg Richter',
      ext_modules=[Extension('mariadb', ['src/mariadb.c', 'src/mariadb_connection.c', 'src/mariadb_methods.c', 'src/mariadb_exception.c', 'src/mariadb_cursor.c', 'src/mariadb_codecs.c'], 
      include_dirs=mariadb_includes,
      library_dirs= mariadb_lib_dirs,
      libraries= mariadb_libraries,
      extra_objects=['./libmariadb/bld/libmariadb/libmariadbclient.a']
      )],
      )

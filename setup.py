#!/usr/bin/env python

import os
import sys
import subprocess

from distutils.core import setup, Extension

def build_libmariadb(build_type):
  if build_type != "Debug" and build_type != "RelWithDebInfo" and build_type != "Release":
    raise Exception("Invalid value for build type")

  if not os.path.isfile('libmariadb/CMakeLists.txt'):
    subprocess.call('git submodule update --init --recursive && mkdir libmariadb/bld', shell=True)

  if sys.platform == "win32":
    build_libmariadb= "cd libmariadb/bld && cmake .. && cmake --build . --config %s" % build_type
  else:
    build_libmariadb= "cd libmariadb/bld && cmake .. -DCMAKE_BUILD_TYPE=%s && make -j4" % build_type
  subprocess.call(build_libmariadb, shell=True)

build_libmariadb("Debug")

mariadb_includes=["libmariadb/include", "libmariadb/bld/include", "./include"]
if not sys.platform == "win32":
  mariadb_lib_dirs=["libmariadb/bld/libmariadb"]
  mariadb_libraries=["dl","m","pthread","ssl","crypto"]
  static_lib="libmariadb/bld/libmariadb/libmariadbclient.a"
else:
  mariadb_lib_dirs=["libmariadb/bld/libmariadb/%s" % build_type]
  mariadb_libraries=[]
  static_lib = "libmariadb/bld/libmariadb/%s/mysqlclient.lib" % build_type

setup(name='mariadb',
      version='0.9.1',
      description='Python MariaDB extension',
      author='Georg Richter',
      url='http://www.mariadb.com',
      ext_modules=[Extension('mariadb', ['src/mariadb.c', 'src/mariadb_connection.c', 'src/mariadb_exception.c', 'src/mariadb_cursor.c', 'src/mariadb_codecs.c', 'src/mariadb_field.c', 'src/mariadb_dbapitype.c', 'src/mariadb_indicator.c'],
      include_dirs=mariadb_includes,
      library_dirs= mariadb_lib_dirs,
      libraries= mariadb_libraries,
      extra_objects=[static_lib]
      )],
      )

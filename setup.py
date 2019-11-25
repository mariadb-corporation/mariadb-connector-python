#!/usr/bin/env python

import os

from distutils.core import setup, Extension

if os.name == "posix":
    from mariadb_posix import get_config
if os.name == "nt":
    from mariadb_windows import get_config

cfg = get_config()

print(cfg.extra_objects)

setup(name='mariadb',
      version='0.9.4',
      classifiers = [
          'Development Status :: 3 - Alpha',
          'Environment :: Console',
          'Environment :: MacOS X',
          'Environment :: Win32 (MS Windows)',
          'Environment :: Posix',
          'License :: OSI Approved :: GNU Lesser General Public License v2 or later (LGPLv2+)',
          'Programming Language :: C',
          'Programming Language :: Python',
          'Programming Language :: Python :: 3.6',
          'Programming Language :: Python :: 3.7',
          'Programming Language :: Python :: 3.8',
          'Operating System :: Microsoft :: Windows',
          'Operating System :: MacOS',
          'Operating System :: POSIX',
          'Intended Audience :: End Users/Desktop',
          'Intended Audience :: Developers',
          'Intended Audience :: System Administrators',
          'Topic :: Database'
      ],
      description='Python MariaDB extension',
      author='Georg Richter',
      license='LGPL 2.1',
      url='https://www.github.com/MariaDB/mariadb-connector-python',
      ext_modules=[Extension('mariadb', ['src/mariadb.c', 'src/mariadb_connection.c',
                                         'src/mariadb_exception.c', 'src/mariadb_cursor.c',
                                         'src/mariadb_codecs.c', 'src/mariadb_field.c',
                                         'src/mariadb_parser.c',
                                         'src/mariadb_pooling.c',
                                         'src/mariadb_dbapitype.c', 'src/mariadb_indicator.c'],
                             include_dirs=cfg.includes,
                             library_dirs=cfg.lib_dirs,
                             libraries=cfg.libs
                             )],
      )

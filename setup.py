#!/usr/bin/env python

import os

from setuptools import setup, Extension
from configparser import ConfigParser

# read the contents of your README file
from os import path
this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

define_macros= [] 

# read settings from site.cfg 
c= ConfigParser()
c.read(['site.cfg'])
options= dict(c.items('cc_options'))

if os.name == "posix":
    from mariadb_posix import get_config
if os.name == "nt":
    from mariadb_windows import get_config

cfg = get_config(options)

PY_MARIADB_AUTHORS= "Georg Richter"

PY_MARIADB_MAJOR_VERSION=0
PY_MARIADB_MINOR_VERSION=9
PY_MARIADB_PATCH_VERSION=59
PY_MARIADB_PRE_RELEASE_SEGMENT="b"

PY_MARIADB_VERSION= "%s.%s.%s" % (PY_MARIADB_MAJOR_VERSION, PY_MARIADB_MINOR_VERSION, PY_MARIADB_PATCH_VERSION)

# Since we increase patch version even for alpha/beta/rc, pre release nr will be always zero.
PY_MARIADB_PRE_RELEASE_NR=0

define_macros.append(("PY_MARIADB_VERSION", "\"%s\"" % PY_MARIADB_VERSION))
define_macros.append(("PY_MARIADB_MAJOR_VERSION", PY_MARIADB_MAJOR_VERSION))
define_macros.append(("PY_MARIADB_MINOR_VERSION", PY_MARIADB_MINOR_VERSION))
define_macros.append(("PY_MARIADB_PATCH_VERSION", PY_MARIADB_PATCH_VERSION))
define_macros.append(("PY_MARIADB_PRE_RELEASE_SEGMENT", "\"%s\"" % PY_MARIADB_PRE_RELEASE_SEGMENT))
define_macros.append(("PY_MARIADB_AUTHORS", "\"%s\"" % PY_MARIADB_AUTHORS))

setup(name='mariadb',
      version=PY_MARIADB_VERSION,
      python_requires='>=3.6',
      classifiers = [
          'Development Status :: 4 - Beta',
          'Environment :: Console',
          'Environment :: MacOS X',
          'Environment :: Win32 (MS Windows)',
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
      long_description=long_description,
      long_description_content_type='text/markdown',
      author=PY_MARIADB_AUTHORS,
      license='LGPL 2.1',
      url='https://www.github.com/mariadb-corporation/mariadb-connector-python',
      project_urls={
         "Bug Tracker": "https://jira.mariadb.org/",
         "Documentation": "https://github.com/mariadb-corporation/mariadb-connector-python/wiki",
         "Source Code": "https://www.github.com/mariadb-corporation/mariadb-connector-python",
      },
      ext_modules=[Extension('mariadb', ['src/mariadb.c', 'src/mariadb_connection.c',
                                         'src/mariadb_exception.c', 'src/mariadb_cursor.c',
                                         'src/mariadb_codecs.c', 'src/mariadb_field.c',
                                         'src/mariadb_parser.c',
                                         'src/mariadb_pooling.c',
                                         'src/mariadb_dbapitype.c', 'src/mariadb_indicator.c'],
                             define_macros= define_macros,
                             include_dirs=cfg.includes,
                             library_dirs=cfg.lib_dirs,
                             libraries=cfg.libs,
                             extra_compile_args = cfg.extra_compile_args,
                             extra_link_args = cfg.extra_link_args,
                             extra_objects= cfg.extra_objects
                             )],
      )

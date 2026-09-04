#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

"""
Unit guard for the default user name: when no ``user`` is given, the
pure-Python Configuration must fall back to the OS login name the way
libmariadb's ``read_user_name`` does, instead of sending an empty user name
(which the server rejects with "Access denied for user ''@...").
"""

import os
import sys
import unittest
from unittest import mock

from mariadb.impl.configuration import Configuration, default_os_user


class DefaultOsUserTest(unittest.TestCase):

    def test_returns_non_empty_string(self) -> None:
        name = default_os_user()
        self.assertIsInstance(name, str)
        self.assertTrue(name)

    @unittest.skipIf(sys.platform.startswith('win'), "POSIX-only branch")
    def test_root_when_euid_is_zero(self) -> None:
        with mock.patch.object(os, 'geteuid', return_value=0):
            self.assertEqual(default_os_user(), 'root')

    @unittest.skipIf(sys.platform.startswith('win'), "POSIX-only branch")
    def test_passwd_entry_of_effective_uid(self) -> None:
        import pwd
        entry = pwd.struct_passwd(('dbuser', 'x', 4242, 4242, '', '/', '/bin/sh'))
        with mock.patch.object(os, 'geteuid', return_value=4242), \
                mock.patch.object(pwd, 'getpwuid', return_value=entry):
            self.assertEqual(default_os_user(), 'dbuser')

    @unittest.skipIf(sys.platform.startswith('win'), "POSIX-only branch")
    def test_environment_fallback_when_no_passwd_entry(self) -> None:
        import pwd
        env = {'LOGNAME': 'from_logname'}
        with mock.patch.object(os, 'geteuid', return_value=4242), \
                mock.patch.object(pwd, 'getpwuid', side_effect=KeyError(4242)), \
                mock.patch.object(os, 'getlogin', side_effect=OSError()), \
                mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(default_os_user(), 'from_logname')

    @unittest.skipIf(sys.platform.startswith('win'), "POSIX-only branch")
    def test_unknown_user_as_last_resort(self) -> None:
        import pwd
        with mock.patch.object(os, 'geteuid', return_value=4242), \
                mock.patch.object(pwd, 'getpwuid', side_effect=KeyError(4242)), \
                mock.patch.object(os, 'getlogin', side_effect=OSError()), \
                mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(default_os_user(), 'UNKNOWN_USER')

    def test_windows_uses_username_variable(self) -> None:
        with mock.patch.object(sys, 'platform', 'win32'), \
                mock.patch.dict(os.environ, {'USERNAME': 'winuser'}, clear=True):
            self.assertEqual(default_os_user(), 'winuser')
        with mock.patch.object(sys, 'platform', 'win32'), \
                mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(default_os_user(), 'ODBC')


class ConfigurationDefaultUserTest(unittest.TestCase):

    def test_unset_user_defaults_to_os_login(self) -> None:
        c = Configuration.from_dict({})
        self.assertEqual(c.user, default_os_user())

    def test_none_user_defaults_to_os_login(self) -> None:
        c = Configuration.from_dict({'user': None})
        self.assertEqual(c.user, default_os_user())

    def test_empty_user_defaults_to_os_login(self) -> None:
        # libmariadb treats an empty user name like an unset one
        c = Configuration.from_dict({'user': ''})
        self.assertEqual(c.user, default_os_user())

    def test_explicit_user_is_kept(self) -> None:
        c = Configuration.from_dict({'user': 'explicit'})
        self.assertEqual(c.user, 'explicit')

    def test_username_alias_is_kept(self) -> None:
        c = Configuration.from_dict({'username': 'alias'})
        self.assertEqual(c.user, 'alias')

    def test_option_file_user_is_kept(self) -> None:
        with mock.patch('mariadb.impl.option_file.read_option_files',
                        return_value={'user': 'from_cnf'}):
            c = Configuration.from_dict({'default_file': '/dev/null'})
        self.assertEqual(c.user, 'from_cnf')


if __name__ == "__main__":
    unittest.main()

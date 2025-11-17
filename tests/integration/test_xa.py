#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import unittest
import mariadb

from ..base_test import create_connection


class TestCA(unittest.TestCase):

    def setUp(self):
        self.connection = create_connection()
        self.connection.autocommit = False

    def tearDown(self):
        self.connection.close()

    def test_xid(self):
        con = create_connection()
        try:
            xid = con.xid(1, "foo", "bar")
            self.assertEqual(xid, (1, "foo", "bar"))

            # default for format_id is 1
            xid = con.xid(0, "foo", "bar")
            self.assertEqual(xid, (1, "foo", "bar"))

            # parameter too long:
            try:
                xid = con.xid(0, "a" * 65, "bar")
            except mariadb.ProgrammingError:
                pass
            try:
                xid = con.xid(0, "foo", "b" * 65)
            except mariadb.ProgrammingError:
                pass
        finally:
            con.close()

    def test_tpc_begin(self):
        con = create_connection()
        try:
            xid = con.xid(0, "1234567890", "2345")
            try:
                con.tpc_begin(xid)
            except mariadb.NotSupportedError:
                pass
        finally:
            con.close()

    def test_tpc_begin_no_xid(self):
        with create_connection() as con:
            try:
                con.tpc_begin(123)
            except mariadb.ProgrammingError:
                pass

    def test_tpc_commit(self):
        con = create_connection()
        xid = con.xid(0, "1234567891", "2345")
        cursor = con.cursor()
        cursor.execute("DROP TABLE IF EXISTS t1")
        cursor.execute("CREATE TABLE t1 (a int)")
        try:
            con.tpc_begin(xid)
            cursor.execute("INSERT INTO t1 VALUES (1),(2)")
            cursor.close()
            with self.assertRaises(mariadb.ProgrammingError) as cm:
                con.tpc_commit()
            self.assertIn("not prepared", str(cm.exception).lower())
        finally:
            con.close()

    def test_tpc_commit2(self):
        con = create_connection()
        xid = con.xid(0, "1234567891", "2345")
        cursor = con.cursor()
        cursor.execute("DROP TABLE IF EXISTS t1")
        cursor.execute("CREATE TABLE t1 (a int)")
        try:
            con.tpc_begin(xid)
            cursor.execute("INSERT INTO t1 VALUES (1),(2)")
            con.tpc_commit(xid)
        finally:
            con.close()

    def test_tpc_rollback_without_prepare(self):
        con = create_connection()
        try:
            xid = con.xid(0, "1234567892", "2345")
            con.tpc_begin(xid)
            cursor = con.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            con.tpc_rollback()
        finally:
            con.close()

    def test_tpc_commit_with_prepare(self):
        con = create_connection()
        try:
            xid = con.xid(0, "1234567893", "2345")
            con.tpc_begin(xid)
            cursor = con.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            con.tpc_prepare()
            con.tpc_commit()
        finally:
            con.close()

    def test_tpc_rollback_with_prepare(self):
        con = create_connection()
        try:
            with self.assertRaises(mariadb.ProgrammingError):
                con.tpc_prepare()

            xid = con.xid(0, "1234567894", "2345")
            con.tpc_begin(xid)
            cursor = con.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            con.tpc_prepare()
            with self.assertRaises(mariadb.ProgrammingError):
                con.tpc_prepare()
            con.tpc_rollback()
        finally:
            con.close()

    def test_tpc_begin_in_transaction_fails(self):
        con = create_connection()
        try:
            xid = con.xid(0, "1234567895", "2345")

            cursor = con.cursor()
            cursor.execute("BEGIN")
            cursor.execute("SELECT 1")
            cursor.close()
            self.assertRaises(mariadb.IntegrityError,
                              con.tpc_begin, xid)
        finally:
            con.close()

    def test_commit_in_tpc_fails(self):
        con = create_connection()
        try:
            xid = con.xid(0, "1234567897", "2345")
            con.tpc_begin(xid)

            self.assertRaises(mariadb.ProgrammingError, con.commit)
        finally:
            con.close()

    def test_rollback_in_tpc_fails(self):
        # calling rollback() within a TPC transaction fails with
        # ProgrammingError.
        con = create_connection()
        try:
            xid = con.xid(0, "1234567898", "2345")
            con.tpc_begin(xid)

            self.assertRaises(mariadb.ProgrammingError, con.rollback)
        finally:
            con.close()

    def test_tpc_commit_without_transaction(self):
        """Test tpc_commit fails when transaction not started (TPC_STATE.NONE)"""
        con = create_connection()
        try:
            # Calling tpc_commit without starting a transaction should fail
            with self.assertRaises(mariadb.ProgrammingError) as cm:
                con.tpc_commit()
            self.assertIn("not started", str(cm.exception).lower())
        finally:
            con.close()

    def test_tpc_commit_without_prepare(self):
        """Test tpc_commit fails when transaction not prepared and xid is None"""
        con = create_connection()
        try:
            xid = con.xid(0, "1234567899", "2345")
            con.tpc_begin(xid)
            
            # Calling tpc_commit() without xid and without prepare should fail
            with self.assertRaises(mariadb.ProgrammingError) as cm:
                con.tpc_commit()
            self.assertIn("not prepared", str(cm.exception).lower())
        finally:
            con.close()

    def test_tpc_commit_with_invalid_xid(self):
        """Test tpc_commit fails when xid is not an Xid object"""
        con = create_connection()
        try:
            xid = con.xid(0, "1234567900", "2345")
            con.tpc_begin(xid)
            
            # Calling tpc_commit with invalid xid type should fail
            with self.assertRaises(mariadb.ProgrammingError) as cm:
                con.tpc_commit(123)
            self.assertIn("must be xid", str(cm.exception).lower())
        finally:
            con.close()

    def test_tpc_rollback_without_transaction(self):
        """Test tpc_rollback fails when transaction not started (TPC_STATE.NONE)"""
        con = create_connection()
        try:
            # Calling tpc_rollback without starting a transaction should fail
            with self.assertRaises(mariadb.ProgrammingError) as cm:
                con.tpc_rollback()
            self.assertIn("not started", str(cm.exception).lower())
        finally:
            con.close()

    def test_tpc_rollback_with_invalid_xid(self):
        """Test tpc_rollback fails when xid is not an Xid object"""
        con = create_connection()
        try:
            xid = con.xid(0, "1234567901", "2345")
            con.tpc_begin(xid)
            
            # Calling tpc_rollback with invalid xid type should fail
            with self.assertRaises(mariadb.ProgrammingError) as cm:
                con.tpc_rollback(123)
            self.assertIn("must be xid", str(cm.exception).lower())
        finally:
            con.close()

    def test_tpc_recover(self):
        """Test tpc_recover returns list of pending transaction IDs"""
        con1 = create_connection()
        con2 = create_connection()
        
        try:
            # Create a prepared transaction
            xid = con1.xid(0, "recover_test_1", "branch1")
            con1.tpc_begin(xid)
            cursor = con1.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            con1.tpc_prepare()
            
            # Use a different connection to recover
            recovered = con2.tpc_recover()
            
            # Should return a list
            self.assertIsInstance(recovered, list)
            
            # Should contain our prepared transaction
            # XA RECOVER returns: (formatID, gtrid_length, bqual_length, data)
            # where data = gtrid + bqual concatenated
            found = False
            for xid_tuple in recovered:
                if len(xid_tuple) >= 4:
                    format_id = xid_tuple[0]
                    gtrid_length = xid_tuple[1]
                    bqual_length = xid_tuple[2]
                    data = xid_tuple[3]
                    
                    # Extract gtrid and bqual from concatenated data
                    if isinstance(data, str):
                        data = data.encode()
                    
                    gtrid = data[:gtrid_length]
                    bqual = data[gtrid_length:gtrid_length + bqual_length]
                    
                    if format_id == 1 and gtrid == b"recover_test_1" and bqual == b"branch1":
                        found = True
                        break
            
            self.assertTrue(found, f"Prepared transaction not found in tpc_recover() results: {recovered}")
            
            # Clean up: commit the prepared transaction
            con1.tpc_commit()
            
            # Verify it's no longer in the recovered list
            recovered_after = con2.tpc_recover()
            found_after = False
            for xid_tuple in recovered_after:
                if len(xid_tuple) >= 4:
                    format_id = xid_tuple[0]
                    gtrid_length = xid_tuple[1]
                    bqual_length = xid_tuple[2]
                    data = xid_tuple[3]
                    
                    if isinstance(data, str):
                        data = data.encode()
                    
                    gtrid = data[:gtrid_length]
                    bqual = data[gtrid_length:gtrid_length + bqual_length]
                    
                    if format_id == 1 and gtrid == b"recover_test_1" and bqual == b"branch1":
                        found_after = True
                        break
            
            self.assertFalse(found_after, "Transaction still in tpc_recover() after commit")
            
        finally:
            con1.close()
            con2.close()

    def test_tpc_recover_empty(self):
        """Test tpc_recover returns empty list when no pending transactions"""
        con = create_connection()
        try:
            # Should return an empty list or a list without our transactions
            recovered = con.tpc_recover()
            self.assertIsInstance(recovered, list)
            # We can't assert it's empty because there might be other pending transactions
            # from other tests or connections, but we can verify it's a list
        finally:
            con.close()


if __name__ == '__main__':
    unittest.main()

"""
Unit tests for Xid class
"""

import unittest
import sys
from pathlib import Path

# Add the mariadb source module to the path BEFORE importing
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from mariadb_shared.xid import Xid
from mariadb_shared.exceptions import ProgrammingError


class TestXid(unittest.TestCase):
    """Test Xid class functionality"""
    
    def test_xid_valid_creation(self):
        """Test creating a valid Xid object"""
        xid = Xid(1, "transaction_id", "branch_qualifier")
        self.assertIsInstance(xid, tuple)
        self.assertEqual(xid[0], 1)  # format_id
        self.assertEqual(xid[1], "transaction_id")  # transaction_id
        self.assertEqual(xid[2], "branch_qualifier")  # branch_qualifier
    
    def test_xid_format_id_zero_becomes_one(self):
        """Test that format_id of 0 is converted to 1"""
        xid = Xid(0, "transaction_id", "branch_qualifier")
        self.assertEqual(xid[0], 1)
    
    def test_xid_format_id_not_int_string(self):
        """Test that format_id must be int, not string"""
        with self.assertRaises(ProgrammingError) as cm:
            Xid("1", "transaction_id", "branch_qualifier")
        self.assertIn("argument 1 must be int", str(cm.exception))
        self.assertIn("str", str(cm.exception))
    
    def test_xid_format_id_not_int_float(self):
        """Test that format_id must be int, not float"""
        with self.assertRaises(ProgrammingError) as cm:
            Xid(1.5, "transaction_id", "branch_qualifier")
        self.assertIn("argument 1 must be int", str(cm.exception))
        self.assertIn("float", str(cm.exception))
    
    def test_xid_format_id_not_int_none(self):
        """Test that format_id must be int, not None"""
        with self.assertRaises(ProgrammingError) as cm:
            Xid(None, "transaction_id", "branch_qualifier")
        self.assertIn("argument 1 must be int", str(cm.exception))
        self.assertIn("NoneType", str(cm.exception))
       
    def test_xid_transaction_id_not_str_int(self):
        """Test that transaction_id must be str, not int"""
        with self.assertRaises(ProgrammingError) as cm:
            Xid(1, 123, "branch_qualifier")
        self.assertIn("argument 2 must be str", str(cm.exception))
        self.assertIn("int", str(cm.exception))
    
    def test_xid_transaction_id_not_str_bytes(self):
        """Test that transaction_id must be str, not bytes"""
        with self.assertRaises(ProgrammingError) as cm:
            Xid(1, b"transaction_id", "branch_qualifier")
        self.assertIn("argument 2 must be str", str(cm.exception))
        self.assertIn("bytes", str(cm.exception))
    
    def test_xid_transaction_id_not_str_none(self):
        """Test that transaction_id must be str, not None"""
        with self.assertRaises(ProgrammingError) as cm:
            Xid(1, None, "branch_qualifier")
        self.assertIn("argument 2 must be str", str(cm.exception))
        self.assertIn("NoneType", str(cm.exception))
       
    def test_xid_branch_qualifier_not_str_int(self):
        """Test that branch_qualifier must be str, not int"""
        with self.assertRaises(ProgrammingError) as cm:
            Xid(1, "transaction_id", 456)
        self.assertIn("argument 3 must be str", str(cm.exception))
        self.assertIn("int", str(cm.exception))
    
    def test_xid_branch_qualifier_not_str_bytes(self):
        """Test that branch_qualifier must be str, not bytes"""
        with self.assertRaises(ProgrammingError) as cm:
            Xid(1, "transaction_id", b"branch_qualifier")
        self.assertIn("argument 3 must be str", str(cm.exception))
        self.assertIn("bytes", str(cm.exception))
    
    def test_xid_branch_qualifier_not_str_none(self):
        """Test that branch_qualifier must be str, not None"""
        with self.assertRaises(ProgrammingError) as cm:
            Xid(1, "transaction_id", None)
        self.assertIn("argument 3 must be str", str(cm.exception))
        self.assertIn("NoneType", str(cm.exception))

    def test_xid_combined_length_at_limit(self):
        """Test that combined length of 64 characters is allowed"""
        # 32 + 32 = 64 (exactly at limit)
        xid = Xid(1, "a" * 32, "b" * 32)
        self.assertEqual(len(xid[1]) + len(xid[2]), 64)
    
    def test_xid_combined_length_exceeds_limit(self):
        """Test that combined length exceeding 64 characters raises error"""
        with self.assertRaises(ProgrammingError) as cm:
            # 33 + 32 = 65 (exceeds limit)
            Xid(1, "a" * 33, "b" * 32)
        self.assertIn("combined length", str(cm.exception).lower())
        self.assertIn("64", str(cm.exception))
    
    def test_xid_combined_length_both_exceed_limit(self):
        """Test that combined length with both parts long raises error"""
        with self.assertRaises(ProgrammingError) as cm:
            # 40 + 40 = 80 (exceeds limit)
            Xid(1, "x" * 40, "y" * 40)
        self.assertIn("combined length", str(cm.exception).lower())
        self.assertIn("64", str(cm.exception))
    
    def test_xid_empty_strings_allowed(self):
        """Test that empty strings are allowed for transaction_id and branch_qualifier"""
        xid = Xid(1, "", "")
        self.assertEqual(xid[1], "")
        self.assertEqual(xid[2], "")
    
    def test_xid_empty_transaction_id_only(self):
        """Test that empty transaction_id with non-empty branch_qualifier is allowed"""
        xid = Xid(1, "", "branch")
        self.assertEqual(xid[1], "")
        self.assertEqual(xid[2], "branch")
    
    def test_xid_empty_branch_qualifier_only(self):
        """Test that empty branch_qualifier with non-empty transaction_id is allowed"""
        xid = Xid(1, "transaction", "")
        self.assertEqual(xid[1], "transaction")
        self.assertEqual(xid[2], "")
    
    def test_xid_negative_format_id(self):
        """Test that negative format_id is allowed"""
        xid = Xid(-1, "transaction_id", "branch_qualifier")
        self.assertEqual(xid[0], -1)
    
    def test_xid_large_format_id(self):
        """Test that large format_id is allowed"""
        xid = Xid(999999, "transaction_id", "branch_qualifier")
        self.assertEqual(xid[0], 999999)
    
    def test_xid_is_tuple(self):
        """Test that Xid is a tuple subclass"""
        xid = Xid(1, "transaction_id", "branch_qualifier")
        self.assertIsInstance(xid, tuple)
        self.assertEqual(len(xid), 3)
    
    def test_xid_tuple_unpacking(self):
        """Test that Xid can be unpacked like a tuple"""
        xid = Xid(1, "transaction_id", "branch_qualifier")
        format_id, transaction_id, branch_qualifier = xid
        self.assertEqual(format_id, 1)
        self.assertEqual(transaction_id, "transaction_id")
        self.assertEqual(branch_qualifier, "branch_qualifier")


if __name__ == '__main__':
    unittest.main()

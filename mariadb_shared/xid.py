# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2020-2025 MariaDB Corporation Ab


# XID class for TPC transactions
from .exceptions import ProgrammingError

_MAX_TPC_XID_SIZE = 64

class Xid(tuple):
    """
    Transaction ID object for two-phase commit transactions.
    
    This class represents a transaction ID (XID) for use with TPC (two-phase commit)
    transactions. The XID consists of three parts:
    - format_id: Format identifier
    - transaction_id: Global transaction identifier
    - branch_qualifier: Branch qualifier
    
    The combined length of transaction_id and branch_qualifier
    is limited to 64 characters.
    """
    def __new__(cls, format_id: int, transaction_id: str, branch_qualifier: str):
        if not isinstance(format_id, int):
            raise ProgrammingError("argument 1 must be int, not %s",
                                            type(format_id).__name__)
        if not isinstance(transaction_id, str):
            raise ProgrammingError("argument 2 must be str, not %s",
                                            type(transaction_id).__name__)
        if not isinstance(branch_qualifier, str):
            raise ProgrammingError("argument 3 must be str, not %s",
                                            type(branch_qualifier).__name__)
        if len(transaction_id) + len(branch_qualifier) > _MAX_TPC_XID_SIZE:
            raise ProgrammingError("combined length of transaction_id and "
                                            "branch_qualifier must not exceed %d characters",
                                            _MAX_TPC_XID_SIZE)
        
        if format_id == 0:
            format_id = 1
        return tuple.__new__(cls, (format_id, transaction_id, branch_qualifier))

"""
CLIENT constants backward-compatibility alias for the CAPABILITY flags in 1.1 branch.
1.1-style imports::

    import mariadb.constants.CLIENT
    from mariadb.constants.CLIENT import FOUND_ROWS

"""

from mariadb_shared.constants.CAPABILITY import *  # noqa: F403

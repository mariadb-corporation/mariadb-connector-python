'''
MariaDB indicator variables

Indicator values are used in executemany() method of cursor class to
indicate special values.
'''

import mariadb._mariadb as m

NULL = m.indicator_null
DEFAULT = m.indicator_default
IGNORE = m.indicator_ignore
IGNORE_ROW = m.indicator_row

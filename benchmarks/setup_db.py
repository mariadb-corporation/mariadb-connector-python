

def init_db(conn):
    cursor=conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS str_test")
    cursor.execute("CREATE TABLE str_test (col1 varchar(200), col2 TEXT, col3 TEXT)")
    vals = [('A' * 200, 'A' * 254, 'A' * 0xFFF) for i in range(100)]
    cursor.executemany("INSERT INTO str_test VALUES (%s, %s, %s)", vals)
    del cursor
    
    cursor=conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS num_test")
    cursor.execute("CREATE TABLE num_test(col1 smallint, col2 int, col3 smallint, col4 bigint, col5 float, col6 decimal(10,5) )")
    vals = [(i % 128,0xFF+i,0xFFF+i, 0xFFFF+i, 10000+i+0.3123, 20000+i+0.1234) for i in range(1000)]
    cursor.executemany("INSERT INTO num_test VALUES (%s,%s,%s,%s,%s,%s)", vals)
    conn.commit()
    del cursor


def end_db(conn):
    cursor=conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS num_test")
    del cursor

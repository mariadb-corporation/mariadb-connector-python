

def init_db(conn, paramstyle):
    my_string = "abcdefghi🌟"
    str1 = "".join([my_string]*10)
    str2 = "".join([my_string]*24)
    str3 = "".join([my_string]*1024)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS str_test")
    cursor.execute("CREATE TABLE str_test ("
                   "col1 varchar(200), col2 TEXT, col3 TEXT)")
    vals = [(str1, str2, str3) for i in range(100)]
    if paramstyle == 'qmark':
        cursor.executemany("INSERT INTO str_test VALUES (?, ?, ?)", vals)
    else:
        cursor.executemany("INSERT INTO str_test VALUES (%s, %s, %s)", vals)

    del cursor

    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS num_test")
    cursor.execute("CREATE TABLE num_test("
                   "col1 smallint, col2 int, col3 smallint, "
                   "col4 bigint, col5 float, col6 decimal(10,5) )")
    vals = [(i % 128, 0xFF+i, 0xFFF+i, 0xFFFF+i,
            10000 + i + 0.3123, 20000 + i + 0.1234) for i in range(1000)]
    if paramstyle == 'qmark':
        cursor.executemany("INSERT INTO num_test VALUES (?,?,?,?,?,?)", vals)
    else:
        cursor.executemany("INSERT INTO num_test VALUES (%s,%s,%s,%s,%s,%s)",
                           vals)

    cursor.execute("DROP TABLE IF EXISTS perfTestTextBatch")
    try:
        cursor.execute("INSTALL SONAME 'ha_blackhole'")
    except Error:
        pass
    createTable = "CREATE TABLE perfTestTextBatch (id MEDIUMINT NOT NULL AUTO_INCREMENT,t0 text, PRIMARY KEY (id)) COLLATE='utf8mb4_unicode_ci'"
    try:
        cursor.execute(createTable + " ENGINE = BLACKHOLE")
    except Exception:
        cursor.execute(createTable)

    conn.commit()
    del cursor


def end_db(conn):
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS num_test")
    del cursor

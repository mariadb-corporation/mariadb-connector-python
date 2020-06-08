# Import MariaDB Connector/Python module
import mariadb

# Establish a connection
connection= mariadb.connect(user="myuser", database="test", host="localhost")

cursor= connection.cursor()

# Create a database table
cursor.execute("DROP TABLE IF EXISTS mytest")
cursor.execute("CREATE TABLE mytest(id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,"
               "first_name VARCHAR(100), last_name VARCHAR(100))")


# Populate table with some data
cursor.execute("INSERT INTO mytest(first_name, last_name) VALUES (?,?)",
               ("Robert", "Redford"))

# retrieve data
cursor.execute("SELECT id, first_name, last_name FROM mytest")

# print content
row= cursor.fetchone()
print(*row, sep='\t')

# free resources
cursor.close()
connection.close()

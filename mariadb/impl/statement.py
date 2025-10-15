"""
Statement implementation for MariaDB Connector/Python
"""

class Statement:
    """
    Statement class for executing SQL queries
    """
    
    def __init__(self, connection):
        """
        Initialize statement with connection
        
        Args:
            connection: MariaDB connection object
        """
        self.connection = connection
        self._prepared = False
        self._statement = None
        
    def execute(self, query, parameters=None):
        """
        Execute a SQL query
        
        Args:
            query: SQL query string
            parameters: Query parameters (optional)
            
        Returns:
            Result of the query execution
        """
        if not self.connection or not hasattr(self.connection, '_client'):
            raise RuntimeError("Connection not available")
            
        # Use the connection's client to execute the query
        return self.connection._client.execute(query, parameters)
        
    def prepare(self, query):
        """
        Prepare a SQL statement
        
        Args:
            query: SQL query string to prepare
        """
        self._statement = query
        self._prepared = True
        
    def close(self):
        """
        Close the statement
        """
        self._prepared = False
        self._statement = None

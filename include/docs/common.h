#define __connect__doc__ \
"connect(*args, **kwargs)\n"\
"--\n"\
"\n"\
"Establishes a connection to a database server and returns a connection\n"\
"object.\n\n"\
"Connection parameters are provided as a set of keyword arguments:\n"\
"----------------------\n"\
"host: string\n"\
"    The host name or IP address of the database server\n\n"\
"user: string\n"\
"    The username used to authenticate with the database server\n\n"\
"password: string\n"\
"    The password of the given user\n\n"\
"database: string\n"\
"    database (schema) name to use when connecting with the database\n"\
"    server\n\n"\
"unix_socket: string\n"\
"    The location of the unix socket file to use instead of using an IP port\n"\
"    to connect. If socket authentication is enabled, this can also be used\n"\
"    in place of a password.\n\n"\
"port: integer\n"\
"    port number of the database server. If not specified the default\n"\
"    value of 3306 will be used.\n\n"\
"connect_timeout: integer\n"\
"    connect timeout in seconds\n\n"\
"read_timeout: integer\n"\
"    read timeout in seconds\n\n"\
"write_timeout: integer\n"\
"    write timeout in seconds\n\n"\
"local_infile: boolean\n"\
"    Eenables or disables the use of LOAD DATA LOCAL INFILE statements.\n\n"\
"compress: boolean\n"\
"    Uses the compressed protocol for client server communication. If the\n"\
"    server doesn't support compressed protocol, the default protocol will\n"\
"    be used\n\n"\
"init_command: string\n"\
"    Command(s) which will be executed when connecting and reconnecting to\n"\
"    the database server\n\n"\
"default_file: string\n"\
"    Read options from the specified option file. If the file is an empty\n"\
"    string, default configuration file(s) will be used\n\n"\
"default_group: string\n"\
"    Read options from the specified group\n\n"\
"ssl_key: string\n"\
"    Defines a path to a private key file to use for TLS. This option\n"\
"    requires that you use the absolute path, not a relative path. The\n"\
"    specified key must be in PEM format\n\n"\
"ssl_cert: string\n"\
"    Defines a path to the X509 certificate file to use for TLS.\n"\
"    This option requires that you use the absolute path, not a relative\n"\
"    path. The X609 certificate must be in PEM format.\n\n"\
"ssl_ca: string\n"\
"    Defines a path to a PEM file that should contain one or more X509\n"\
"    certificates for trusted Certificate Authorities (CAs) to use for TLS.\n"\
"    This option requires that you use the absolute path, not a relative\n"\
"    path.\n\n"\
"ssl_capath: string\n"\
"    Defines a path to a directory that contains one or more PEM files that\n"\
"    contains one X509 certificate for a trusted Certificate Authority (CA)\n\n"\
"ssl_cipher: string\n"\
"    Defines a list of permitted cipher suites to use for TLS\n\n"\
"ssl_crl_path: string\n"\
"    Defines a path to a PEM file that should contain one or more revoked\n"\
"    X509 certificates to use for TLS. This option requires that you use\n"\
"    the absolute path, not a relative path.\n\n"\
"ssl_verify_server_cert: boolean\n"\
"    Enables server certificate verification.\n\n"\
"ssl_enforce: Boolean\n"\
"    The connection must use TLS security or it will fail.\n\n"

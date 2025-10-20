from mariadb_shared import constants

field_types = {constants.FIELD_TYPE.DECIMAL: "DECIMAL",
               constants.FIELD_TYPE.TINY:  "TINY",
               constants.FIELD_TYPE.SHORT: "SHORT",
               constants.FIELD_TYPE.LONG: "LONG",
               constants.FIELD_TYPE.FLOAT: "FLOAT",
               constants.FIELD_TYPE.DOUBLE: "DOUBLE",
               constants.FIELD_TYPE.NULL: "NULL",
               constants.FIELD_TYPE.TIMESTAMP: "TIMESTAMP",
               constants.FIELD_TYPE.LONGLONG: "LONGLONG",
               constants.FIELD_TYPE.INT24: "INT24",
               constants.FIELD_TYPE.DATE: "DATE",
               constants.FIELD_TYPE.TIME: "TIME",
               constants.FIELD_TYPE.DATETIME: "DATETIME",
               constants.FIELD_TYPE.YEAR: "YEAR",
               constants.FIELD_TYPE.NEWDATE: "NEWDATE",
               constants.FIELD_TYPE.VARCHAR: "VARCHAR",
               constants.FIELD_TYPE.BIT: "BIT",
               constants.FIELD_TYPE.JSON: "JSON",
               constants.FIELD_TYPE.NEWDECIMAL: "NEWDECIMAL",
               constants.FIELD_TYPE.ENUM: "ENUM",
               constants.FIELD_TYPE.SET: "SET",
               constants.FIELD_TYPE.TINY_BLOB: "TINY_BLOB",
               constants.FIELD_TYPE.MEDIUM_BLOB: "MEDIUM_BLOB",
               constants.FIELD_TYPE.LONG_BLOB: "LONG_BLOB",
               constants.FIELD_TYPE.BLOB: "BLOB",
               constants.FIELD_TYPE.VAR_STRING: "VAR_STRING",
               constants.FIELD_TYPE.STRING: "STRING",
               constants.FIELD_TYPE.GEOMETRY: "GEOMETRY"}

field_flags = {constants.FIELD_FLAG.NOT_NULL: "NOT_NULL",
               constants.FIELD_FLAG.PRIMARY_KEY: "PRIMARY_KEY",
               constants.FIELD_FLAG.UNIQUE_KEY: "UNIQUE_KEY",
               constants.FIELD_FLAG.MULTIPLE_KEY: "PART_KEY",
               constants.FIELD_FLAG.BLOB: "BLOB",
               constants.FIELD_FLAG.UNSIGNED: "UNSIGNED",
               constants.FIELD_FLAG.ZEROFILL: "ZEROFILL",
               constants.FIELD_FLAG.BINARY: "BINARY",
               constants.FIELD_FLAG.ENUM: "NUMERIC",
               constants.FIELD_FLAG.AUTO_INCREMENT: "AUTO_INCREMENT",
               constants.FIELD_FLAG.TIMESTAMP: "TIMESTAMP",
               constants.FIELD_FLAG.SET: "SET",
               constants.FIELD_FLAG.NO_DEFAULT: "NO_DEFAULT",
               constants.FIELD_FLAG.ON_UPDATE_NOW: "UPDATE_TIMESTAMP",
               constants.FIELD_FLAG.NUMERIC: "NUMERIC"}


class fieldinfo():

    def type(self, description):
        if description[1] in field_types:
            return field_types[description[1]]
        return None

    def flag(self, description):
        flags = [field_flags[f] for f in field_flags.keys()
                 if description[7] & f]
        return " | ".join(flags)

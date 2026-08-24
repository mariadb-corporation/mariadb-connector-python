/*****************************************************************************
  Copyright (C) 2019,2020 Georg Richter and MariaDB Corporation AB

  This library is free software; you can redistribute it and/or
  modify it under the terms of the GNU Library General Public
  License as published by the Free Software Foundation; either
  version 2 of the License, or (at your option) any later version.

  This library is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
  Library General Public License for more details.

  You should have received a copy of the GNU Library General Public
  License along with this library; if not see <http://www.gnu.org/licenses>
  or write to the Free Software Foundation, Inc.,
  51 Franklin St., Fifth Floor, Boston, MA 02110, USA
 ****************************************************************************/

#include <mariadb_python.h>

#define IS_WHITESPACE(a) (a==32 || a==9 || a==10 || a==13)
#define IN_LITERAL(p) ((p)->in_literal[0] ||\
                      (p)->in_literal[1] ||\
                      (p)->in_literal[2])

const char *comment_start= "/*";
const char *comment_end= "*/";
const char literals[3]= {'\'', '\"', '`'};

static struct {
    enum enum_binary_command command;
    MrdbString str;
} binary_command[] =
{
    {SQL_INSERT, {"INSERT", 6}},
    {SQL_UPDATE, {"UPDATE", 6}},
    {SQL_REPLACE, {"REPLACE", 7}},
    {SQL_DELETE, {"DELETE", 6}},
    {SQL_CALL, {"CALL", 4}},
    {SQL_DO, {"DO", 2}},
    {SQL_NONE, {NULL, 0}}
};

static uint8_t
check_keyword(char* ofs, char* end, char* keyword, size_t keylen)
{
    int i;

    if ((size_t)(end - ofs) < keylen + 1)
    {
        return 0;
    }

    for (i = 0; i < (int)keylen; i++)
    {
        if (toupper(*(ofs + i)) != keyword[i])
        {
            return 0;
        }
    }

    if (!IS_WHITESPACE(*(ofs + keylen)))
    {
        return 0;
    }
    return 1;
}

void
MrdbParser_end(MrdbParser* p)
{
    if (p)
    {
        if (p->keys)
        {
            uint32_t i;
            /* Use key_count if tracked, or check key pointers safely */
            for (i = 0; i < p->param_count; i++)
            {
                if (p->keys[i].str)
                {
                    MARIADB_FREE_MEM(p->keys[i].str);
                }
            }
            MARIADB_FREE_MEM(p->keys);
        }
        
        MARIADB_FREE_MEM(p->statement.str);

        /* Release list reference if parse failed before ownership transfer */
        Py_CLEAR(p->param_list);

        /* Free the parser struct itself using PyMem_RawFree / MARIADB_FREE_MEM */
        MARIADB_FREE_MEM(p);
    }
}

MrdbParser *
MrdbParser_init(MYSQL *mysql, const char *statement, size_t length)
{
    MrdbParser *p;

    if (!statement || !length)
    {
        return NULL;
    }

    if ((p = PyMem_RawCalloc(1, sizeof(MrdbParser))))
    {
        if (!(p->statement.str = (char *)PyMem_RawCalloc(1, length + 1)))
        {
            MARIADB_FREE_MEM(p);
            return NULL;
        }
        memcpy(p->statement.str, statement, length);
        p->statement.length = length;
        p->mysql = mysql;
        p->param_count = 0;

        if (!(p->param_list = PyList_New(0)))
        {
            MARIADB_FREE_MEM(p->statement.str);
            MARIADB_FREE_MEM(p);
            return NULL;
        }
    }
    return p;
}

static void
parser_error(char *errmsg, size_t errmsg_len, const char *errstr)
{
    if (errmsg_len)
    {
        strncpy(errmsg, errstr, errmsg_len - 1);
    }
}

#define IS_WHITESPACE(a) (a==32 || a==9 || a==10 || a==13)

uint8_t
MrdbParser_parse(MrdbParser *p, uint8_t is_batch,
                 char *errmsg, size_t errmsg_len)
{
    char *a, *end;
    char lastchar = 0;
    PyObject *tmp;

    if (errmsg_len)
        *errmsg = 0;

    if (!p) {
        parser_error(errmsg, errmsg_len, "Parser not initialized");
        return 1;
    }

    if (!p->statement.str || !p->statement.length) {
        parser_error(errmsg, errmsg_len, "Invalid (empty) statement");
        return 1;
    }

    a = p->statement.str;
    end = a + p->statement.length - 1;
    p->in_literal = LIT_NONE;
    p->in_comment = 0;
    p->comment_eol = 0;

    while (a <= end)
    {
        if (!p->in_comment) {
            /* --- literal handling --- */
            switch (p->in_literal) {
                case LIT_NONE:
                    if (*a == '\'') p->in_literal = LIT_SINGLE_QUOTE;
                    else if (*a == '"') p->in_literal = LIT_DOUBLE_QUOTE;
                    else if (*a == '`') p->in_literal = LIT_BACKTICK;
                    break;
                case LIT_SINGLE_QUOTE:
                    if (*a == '\'' && lastchar != '\\')
                        p->in_literal = LIT_NONE;
                    lastchar = *a;
                    a++;
                    continue;

                case LIT_DOUBLE_QUOTE:
                    if (*a == '"' && lastchar != '\\')
                        p->in_literal = LIT_NONE;
                    lastchar = *a;
                    a++;
                    continue;

                case LIT_BACKTICK:
                    if (*a == '`')
                        p->in_literal = LIT_NONE;
                    a++;
                    continue;
            }
        }

        /* --- handle comments --- */
        if (!p->in_comment && p->in_literal == LIT_NONE)
        {
            /* Style 1: C-style comments */
            if (*a == '/' && *(a+1) == '*')
            {
                a += 2;

                /* check special comments starting with ! */
                if (a <= end && *a == '!')
                {
                    if (isspace(*(a+1)) || isdigit(*(a+1)))
                    {
                        p->in_comment = 0; /* treat as special, parse content normally */
                        continue;
                    }
                }

                /* check MariaDB M! comments */
                if (a+1 <= end && *a == 'M' && *(a+1) == '!')
                {
                    a += 2;
                    /* If whitespace or version number, treat as special */
                    if (isspace(*a) || isdigit(*a))
                    {
                        p->in_comment = 0; /* parse normally */
                        continue;
                    }
                }

                /* normal comment */
                p->in_comment = 1;
                continue;
            }

            /* Style 2: hash comment */
            if (*a == '#')
            {
                a++;
                p->comment_eol = 1;
                continue;
            }

            /* Style 3: -- comment */
            if (*a == '-' && *(a+1) == '-' && ((a+2) <= end) && *(a+2) == ' ')
            {
                a += 3;
                p->comment_eol = 1;
                continue;
            }
        }
        else
        {
            /* inside normal C-style comment */
            if (*a == '*' && *(a+1) == '/')
            {
                a += 2;
                p->in_comment = 0;
                continue;
            }
            a++;
            continue;
        }

        if (p->comment_eol)
        {
            if (*a == '\n' || *a == '\0')
            {
                a++;
                p->comment_eol = 0;
                continue;
            }
            a++;
            continue;
        }

        /* --- parameter handling --- */
        if (*a == '?')
        {
            if (p->paramstyle && p->paramstyle != QMARK)
            {
                parser_error(errmsg, errmsg_len,
                             "Mixing different parameter styles is not supported");
                return 1;
            }
            p->paramstyle = QMARK;
            p->param_count++;
            tmp = PyLong_FromLong((long)(a - p->statement.str));
            PyList_Append(p->param_list, tmp);
            Py_DECREF(tmp);
            a++;
            continue;
        }

        /* FORMAT / PYFORMAT handling */
        if (*a == '%' && lastchar != '\\')
        {
            if (*(a+1) == 's' || *(a+1) == 'd')
            {
                if (p->paramstyle && p->paramstyle != FORMAT)
                {
                    parser_error(errmsg, errmsg_len,
                                 "Mixing different parameter styles is not supported");
                    return 1;
                }
                p->paramstyle = FORMAT;
                *a = '?';
                memmove(a+1, a+2, end - a);
                end--;
                tmp = PyLong_FromLong((long)(a - p->statement.str));
                PyList_Append(p->param_list, tmp);
                Py_DECREF(tmp);
                a++;
                p->param_count++;
                continue;
            }

            if (*(a+1) == '(')
            {
                char *val_end = strstr(a+1, ")s");
                if (val_end)
                {
                    ssize_t keylen = val_end - a + 1;
                    if (p->paramstyle && p->paramstyle != PYFORMAT)
                    {
                        parser_error(errmsg, errmsg_len,
                                     "Mixing different parameter styles is not supported");
                        return 1;
                    }
                    p->paramstyle = PYFORMAT;
                    *a = '?';
                    p->param_count++;
                    tmp = PyLong_FromLong((long)(a - p->statement.str));
                    PyList_Append(p->param_list, tmp);
                    Py_DECREF(tmp);

                    if (p->keys)
                    {
                        MrdbString *m;
                        if (!(m = PyMem_RawRealloc(p->keys,
                                                     p->param_count * sizeof(MrdbString))))
                        {
                            parser_error(errmsg, errmsg_len, "Not enough memory");
                            return 1;
                        }
                        p->keys = m;
                    }
                    else
                    {
                        if (!(p->keys = PyMem_RawMalloc(sizeof(MrdbString))))
                        {
                            parser_error(errmsg, errmsg_len, "Not enough memory");
                            return 1;
                        }
                    }
                    if (!(p->keys[p->param_count-1].str = PyMem_RawCalloc(1, keylen-2)))
                    {
                        parser_error(errmsg, errmsg_len, "Not enough memory");
                        return 1;
                    }
                    memcpy(p->keys[p->param_count-1].str, a+2, keylen-3);
                    p->keys[p->param_count-1].length = keylen-3;

                    memmove(a+1, val_end+2, end - a - keylen + 1);
                    a += 1;
                    end -= keylen;
                    continue;
                }
            }
        }

        /* --- batch handling --- */
        if (is_batch)
        {
            if (!p->is_insert && check_keyword(a, end, "INSERT", 6))
            {
                if (lastchar == 0 || IS_WHITESPACE(lastchar) || lastchar == '/')
                {
                    p->is_insert = 1;
                    a += 7;
                }
            }
            if (p->is_insert && check_keyword(a, end, "VALUES", 6))
            {
                p->value_ofs = a + 7;
                a += 7;
                continue;
            }
        }
        else
        {
            if (p->command == SQL_NONE)
            {
                for (uint8_t i=0; binary_command[i].str.str; i++)
                {
                    if (check_keyword(a, end, binary_command[i].str.str,
                                      binary_command[i].str.length))
                    {
                        p->command = binary_command[i].command;
                        break;
                    }
                }
                if (p->command == SQL_NONE)
                    p->command = SQL_OTHER;
            }
        }

        lastchar = *a;
        a++;
    }

    /* Update statement length */
    p->statement.length = end - p->statement.str + 1;
    return 0;
}


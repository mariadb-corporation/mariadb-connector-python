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

typedef struct {
  const char *start;
  char *pos;
  size_t byte_len;
  size_t char_len;
  size_t char_pos;
} utf8_str;

#define isutf8(c) (((c)&0xC0)!=0x80)

uint8_t utf8_len(char *c)
{
  uint8_t i= 0;
  (void)(isutf8(c[++(i)]) || isutf8(c[++(i)]) ||
         isutf8(c[++(i)]) || ++(i));
  return i;
}

size_t utf8_char_cnt(const char *start, size_t bytes)
{
  size_t char_cnt= 0;
  char *tmp= (char *)start;

  while (tmp < start + bytes)
  {
    tmp+= utf8_len(tmp);
    char_cnt++;
  }
  return char_cnt;
}

static void utf8_str_init(utf8_str *u8, const char *stmt, size_t stmt_len)
{
  u8->start= stmt;
  u8->pos= (char *)stmt;
  u8->byte_len= stmt_len;
  u8->char_pos= 0;
  u8->char_len= utf8_char_cnt(u8->start, u8->byte_len);
}

static void utf8_next(utf8_str *u8, size_t inc)
{
  size_t i;

  for (i=0; i < inc; i++)
  {
    u8->pos+= utf8_len(u8->pos);
    u8->char_pos++;
  }
}

static inline uint8_t utf8_chk_size(utf8_str *u8, size_t size)
{
  return (u8->char_pos + size < u8->char_len);
}

static char *utf8_val(utf8_str *u8, size_t offset)
{
  size_t i;
  char *tmp= u8->pos;
  for (i=0; i < offset; i++)
  {
    tmp+= utf8_len(tmp);
  }
  return tmp;
}

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
            for (i=0; i < p->param_count; i++)
            {
                MARIADB_FREE_MEM(p->keys[i].str);
            }
            MARIADB_FREE_MEM(p->keys);
        }
        MARIADB_FREE_MEM(p->statement.str);
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

    if ((p= PyMem_RawCalloc(1, sizeof(MrdbParser))))
    { 
        if (!(p->statement.str = (char *)PyMem_RawCalloc(1, length + 1)))
        {
            MARIADB_FREE_MEM(p);
            return NULL;
        }
        memcpy(p->statement.str, statement, length);
        p->statement.length= length;
        p->mysql= mysql;
        p->param_count= 0;
    }
    p->param_list= PyList_New(0);
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

uint8_t
MrdbParser_parse(MrdbParser *p, uint8_t is_batch,
                 char *errmsg, size_t errmsg_len)
{
    char *end;
    char lastchar= 0;
    uint8_t i;
    utf8_str u8;

    if (errmsg_len)
        *errmsg= 0;

    if (!p)
    {
        parser_error(errmsg, errmsg_len, "Parser not initialized");
        return 1;
    }

    if (!p->statement.str || !p->statement.length)
    {
        parser_error(errmsg, errmsg_len, "Invalid (empty) statement");
        return 1;
    }

    utf8_str_init(&u8, p->statement.str, p->statement.length);
    end= p->statement.str + p->statement.length;

    while (u8.pos <= end)
    {
cont:
        /* we are only interested in ascii chars, so all multibyte characterss
           will be ignored */
        if (utf8_len(u8.pos) > 1)
        {
          utf8_next(&u8, 1);
          continue;
        }
        /* check literals */
        for (i=0; i < 3; i++)
        {
            if (*u8.pos == literals[i])
            {
                p->in_literal[i]= !(p->in_literal[i]);
                utf8_next(&u8, 1);
                goto cont;
            }
        }
        /* nothing to do, if we are inside a comment or literal */
        if (IN_LITERAL(p))
        {
            utf8_next(&u8,1);
            continue;
        }
        /* check comment */
        if (!p->in_comment)
        {
            /* Style 1 */
            if (utf8_chk_size(&u8, 1) && *u8.pos == '/' && *utf8_val(&u8, 1) == '*')
            {
                utf8_next(&u8, 2);
                if (utf8_chk_size(&u8, 1) && *u8.pos == '!')
                {
                    /* check special syntax: 1. comment followed by '!' and whitespace */
                    if (isspace(*utf8_val(&u8,1)))
                    {
                      utf8_next(&u8, 2);
                      continue;
                    }
                    /* check special syntax: 3. comment followed by '!' 5 or 6 digit version number */
                    if (utf8_chk_size(&u8, 7) && isdigit(*utf8_val(&u8,1)))
                    {
                        char *end_number;
                        unsigned long version_number= strtol(utf8_val(&u8,1), &end_number, 10);
                        if ((version_number >= 50700 && version_number <= 99999) ||
                            !(version_number <= mysql_get_server_version(p->mysql)))
                        {
                          p->in_comment= 1;
                        }
                        utf8_next(&u8, end_number - u8.pos);
                        continue;
                    }
                }
                if (utf8_chk_size(&u8, 2) && 
                    *u8.pos == 'M' && *utf8_val(&u8, 1) == '!')
                {
                    utf8_next(&u8, 2);
                    /* check special syntax: 2. comment followed by 'M! ' (MariaDB only) */
                    if (isspace(*(u8.pos)))
                        continue;

                    /* check special syntax: 2. comment followed by 'M!' and version number */
                    if (utf8_chk_size(&u8, 6) && isdigit(*u8.pos))
                    {
                      char *end_number;
                      unsigned long version_number= strtol(u8.pos, &end_number, 10);
                      if (!(version_number <= mysql_get_server_version(p->mysql)))
                      {
                          p->in_comment= 1;
                      }
                      utf8_next(&u8, end_number - u8.pos);
                      continue;
                    }
                }
                p->in_comment= 1;
                continue;
            }
            /* Style 2 */
            if (*u8.pos == '#')
            {
                utf8_next(&u8, 1);
                p->comment_eol= 1;
                continue;
            }
            /* Style 3 */
            if (utf8_chk_size(&u8, 1) && *u8.pos == '-' && *(utf8_val(&u8,1)) == '-')
            {
                if (utf8_chk_size(&u8, 3) && *(utf8_val(&u8,2)) == ' ')
                {
                    utf8_next(&u8, 3);
                    p->comment_eol= 1;
                    continue;
                }
            }
        } else
        {
            if (utf8_chk_size(&u8, 1) &&
                *u8.pos == '*' && *(utf8_val(&u8, 1)) == '/')
            {
                utf8_next(&u8, 2);
                p->in_comment= 0;
                continue;
            } else {
                utf8_next(&u8, 1);
                continue;
            } 
        }
        if (p->comment_eol) {
            if (*u8.pos == '\0' || *u8.pos == '\n')
            {
                utf8_next(&u8, 1);
                p->comment_eol= 0;
                continue;
            }
            utf8_next(&u8, 1);
            continue;
        }
        /* checking for different paramstyles */
        /* parmastyle = qmark */
        if (*u8.pos == '?')
        {
            PyObject *tmp;
            if (p->paramstyle && p->paramstyle != QMARK)
            {
                parser_error(errmsg, errmsg_len,
                    "Mixing different parameter styles is not supported");
                return 1;
            }
            p->paramstyle= QMARK;
            p->param_count++;
            tmp= PyLong_FromLong((long)u8.char_pos);
            PyList_Append(p->param_list, tmp);
            Py_DECREF(tmp);
            utf8_next(&u8, 1);
            continue;
        }

        if (*u8.pos == '%' && lastchar != '\\')
        {
            /* paramstyle format */
            if (utf8_chk_size(&u8, 1) && 
               (*utf8_val(&u8, 1) == 's' || *utf8_val(&u8, 1) == 'd'))
            {
                PyObject *tmp;
                if (p->paramstyle && p->paramstyle != FORMAT)
                {
                    parser_error(errmsg, errmsg_len, 
                       "Mixing different parameter styles is not supported");
                    return 1;
                }
                p->paramstyle= FORMAT;
                *u8.pos= '?';
                memmove(u8.pos +1, u8.pos + 2, end - u8.pos);
                u8.char_len--;
                u8.byte_len--;
                end--;

                tmp= PyLong_FromLong((long)(u8.char_pos));
                PyList_Append(p->param_list, tmp);
                Py_DECREF(tmp);
                utf8_next(&u8,1);
                p->param_count++;
                continue;
            }
            if (utf8_chk_size(&u8,3) && *(utf8_val(&u8, 1)) == '(')
            {
                /* named parameter: %(param_name)s */
                char *val_end= strstr(u8.pos+1, ")s");
                PyObject *tmp;
                MrdbString *m;

                if (val_end)
                {
                    ssize_t keylen= val_end - u8.pos + 1;
                    ssize_t char_len= utf8_char_cnt(u8.pos + 1, keylen);
                    if (p->paramstyle && p->paramstyle != PYFORMAT)
                    {
                        parser_error(errmsg, errmsg_len, 
                          "Mixing different parameter styles is not supported");
                        return 1;
                    }
                    p->paramstyle= PYFORMAT;
                    *u8.pos= '?';
                    p->param_count++;
                    tmp= PyLong_FromLong((long)u8.char_pos);
                    PyList_Append(p->param_list, tmp);
                    Py_DECREF(tmp);
                    if (!(m= PyMem_RawRealloc(p->keys, 
                          p->param_count * sizeof(MrdbString))))
                    {
                       parser_error(errmsg, errmsg_len, 
                       "Not enough memory");
                       return 1;
                    }
                    p->keys= m;

                    if (!(p->keys[p->param_count - 1].str= 
                        PyMem_RawCalloc(1, keylen - 2)))
                    {
                        parser_error(errmsg, errmsg_len, "Not enough memory");
                        return 1;
                    }
                    memcpy(p->keys[p->param_count - 1].str, u8.pos + 2, keylen - 3);
                    p->keys[p->param_count - 1].length= keylen - 3;

                    memmove(u8.pos+1, val_end+2, end - u8.pos - keylen + 1);
                    u8.byte_len-= keylen;
                    u8.char_len-= char_len;
                    utf8_next(&u8,1);
                    end -= keylen;
                    continue;
                }
            }
        }

        if (is_batch)
        {
            /* Do we have an insert statement ? */
            if (!p->is_insert && check_keyword(u8.pos, end, "INSERT", 6))
            {
                if (lastchar == 0 ||
                    (IS_WHITESPACE(lastchar)) ||
                     lastchar == '/')
                {
                    p->is_insert = 1;
                    utf8_next(&u8, 7);
                }
            }

            if (p->is_insert && check_keyword(u8.pos, end, "VALUES", 6))
            {
                p->value_ofs = u8.pos + 7;
                utf8_next(&u8, 7);
                continue;
            }
        } 
        else {
          /* determine SQL command */
          if (p->command == SQL_NONE)
          {
            for (uint8_t i=0; binary_command[i].str.str; i++)
            {
              if (check_keyword(u8.pos, end, binary_command[i].str.str,
                  binary_command[i].str.length))
              {
                p->command= binary_command[i].command;
                break;
              }
            }
            if (p->command == SQL_NONE)
              p->command= SQL_OTHER;
          }

        }
        lastchar= *u8.pos;
        utf8_next(&u8, 1);
    }
    /* Update length */
    p->statement.length= end - p->statement.str + 1;
    return 0;
}

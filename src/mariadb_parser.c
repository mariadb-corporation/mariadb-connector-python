/************************************************************************************
    Copyright (C) 2019 Georg Richter and MariaDB Corporation AB

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
*************************************************************************************/

#include <mariadb_python.h>

#define IS_WHITESPACE(a) (a==32 || a==9 || a==10 || a==13)
#define IN_LITERAL(p) ((p)->in_literal[0] || (p)->in_literal[1] || (p)->in_literal[2])

const char *comment_start= "/*";
const char *comment_end= "*/";
const char literals[3]= {'\'', '\"', '`'};

static uint8_t check_keyword(char* ofs, char* end, char* keyword, size_t keylen)
{
  int i;

  if ((size_t)(end - ofs) < keylen + 1)
    return 0;
  for (i = 0; i < (int)keylen; i++)
    if (toupper(*(ofs + i)) != keyword[i])
      return 0;
  if (!IS_WHITESPACE(*(ofs + keylen)))
    return 0;
  return 1;
}

void MrdbParser_end(MrdbParser* p)
{
  if (p)
  {
    MARIADB_FREE_MEM(p->statement.str);
    MARIADB_FREE_MEM(p);
  }
}

MrdbParser *MrdbParser_init(const char *statement, size_t length)
{
  MrdbParser *p;

  if (!statement || !length)
    return NULL;

  if ((p= PyMem_RawCalloc(1, sizeof(MrdbParser))))
  { 
    if (!(p->statement.str = PyMem_RawCalloc(1, length + 1)))
    {
      MARIADB_FREE_MEM(p);
      return NULL;
    }
    memcpy(p->statement.str, statement, length);
    p->statement.length= length;
  }
  return p;
}


void MrdbParser_parse(MrdbParser *p, uint8_t is_batch)
{
  char *a, *end;
  char lastchar= 0;
  uint8_t i;

  if (!p || !p->statement.str)
    return;

  a= p->statement.str;
  end= a + p->statement.length - 1;

  while (a <= end)
  {
    /* check literals */
    for (i=0; i < 3; i++)
    {
      if (*a == literals[i])
      {
        p->in_literal[i]= !(p->in_literal[i]);
        a++;
        continue;
      }
    }
    /* nothing to do, if we are inside a comment or literal */
    if (IN_LITERAL(p))
    {
      a++;
      continue;
    }
    /* check comment */
    if (!p->in_comment)
    {
      /* Style 1 */
      if (*a == '/' && *(a + 1) == '*')
      {
        a+= 2;
        p->in_comment= 1;
        continue;
      }
      /* Style 2 */
      if (*a == '#')
      {
        a++;
        p->comment_eol= 1;
      }
      /* Style 3 */
      if (*a == '-' && *(a+1) == '-')
      {
        if (((a+2) < end) && *(a+2) == ' ')
        {
          a+= 3;
          p->comment_eol= 1;
        }
      }
    } else
    {
      if (*a == '*' && *(a + 1) == '/')
      {
        a+= 2;
        p->in_comment= 0;
        continue;
      } else {
        a++;
        continue;
      } 
    }
    if (p->comment_eol) {
      if (*a == '\0' || *a == '\n')
      {
        a++;
        p->comment_eol= 0;
        continue;
      }
      a++;
      continue;
    }
    /* checking for different paramstyles */
    /* parmastyle = qmark */
    if (*a == '?')
    {
      p->param_count++;
      a++;
      continue;
    }

    /* paramstype = pyformat */
    if (*a == '%' && lastchar != '\\')
    {
      if (*(a+1) == 's' || *(a+1) == 'd')
      {
        *a= '?';
        memmove(a+1, a+2, end - a);
        end--;
        a++;
        p->param_count++;
        continue;
      }
      if (*(a+1) == '(')
      {
        char *val_end= strstr(a+1, ")s");
        if (val_end)
        {
          int keylen= val_end - a + 1;
          *a= '?';
          p->param_count++;
          memmove(a+1, val_end+2, end - a - keylen);
          end -= keylen;
          continue;
        }
      }
    }

    if (is_batch)
    {
      /* Do we have an insert statement ? */
      if (!p->is_insert && check_keyword(a, end, "INSERT", 6))
      {
        if (lastchar == 0 || (IS_WHITESPACE(lastchar)) || lastchar == '/')
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
    
    lastchar= *a;
    a++;
  }
  /* Update length */
  p->statement.length= end - p->statement.str + 1;
}

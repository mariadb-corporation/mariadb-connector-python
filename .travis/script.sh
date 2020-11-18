#!/bin/bash

set -x
set -e

###################################################################################################################
# test different type of configuration
###################################################################################################################
mysql=( mysql --protocol=tcp -ubob -h127.0.0.1 --port=3305 )
if [ -n "$SKYSQL" ] ; then

  if [ -z "$SKYSQL_TEST_HOST" ] ; then
    echo "No SkySQL configuration found !"
    exit 1
  fi

  export TEST_USER=$SKYSQL_TEST_USER
  export TEST_HOST=$SKYSQL_TEST_HOST
  export TEST_PASSWORD=$SKYSQL_TEST_PASSWORD
  export TEST_PORT=$SKYSQL_TEST_PORT
  export TEST_DATABASE=$SKYSQL_TEST_DATABASE
else
  if [ "$DB" = "build" ] ; then
    .travis/build/build.sh
    docker build -t build:latest --label build .travis/build/
  fi


  export ENTRYPOINT=$PROJ_PATH/.travis/entrypoint

  if [ -n "$MAXSCALE_VERSION" ] ; then
    ###################################################################################################################
    # launch Maxscale with one server
    ###################################################################################################################
    export COMPOSE_FILE=.travis/maxscale-compose.yml
    export ENTRYPOINT=$PROJ_PATH/.travis/sql
    docker-compose -f ${COMPOSE_FILE} build
    docker-compose -f ${COMPOSE_FILE} up -d
    mysql=( mysql --protocol=tcp -ubob -h127.0.0.1 --port=4007 )
  else
    docker-compose -f .travis/docker-compose.yml up -d
  fi

  for i in {60..0}; do
      if echo 'SELECT 1' | "${mysql[@]}" &> /dev/null; then
          break
      fi
      echo 'data server still not active'
      sleep 1
  done

  if [ -z "$MAXSCALE_VERSION" ] ; then
    docker-compose -f .travis/docker-compose.yml exec -u root db bash /pam/pam.sh
    sleep 1
    docker-compose -f .travis/docker-compose.yml stop db
    sleep 1
    docker-compose -f .travis/docker-compose.yml up -d
    docker-compose -f .travis/docker-compose.yml logs db

    for i in {60..0}; do
      if echo 'SELECT 1' | "${mysql[@]}" &> /dev/null; then
          break
      fi
      echo 'data server still not active'
      sleep 1
    done
  fi
fi

if [ -n "$BENCH" ] ; then
#  pyenv install pypy3.6-7.2.0
#  pyenv install miniconda3-4.3.30
  pyenv install 3.8.0


  export PYENV_VERSION=3.8.0
  python setup.py build
  python setup.py install
  pip install mysql-connector-python pyperf
  export TEST_MODULE=mariadb
  cd testing
  python bench_init.py
  python bench.py -o mariadb_bench.json --inherit-environ=TEST_USER,TEST_HOST,TEST_PORT,TEST_MODULE
  export TEST_MODULE=mysql.connector
  python bench.py -o mysql_bench.json --inherit-environ=TEST_USER,TEST_HOST,TEST_PORT,TEST_MODULE

  python -m pyperf compare_to mysql_bench.json mariadb_bench.json --table
  cd ..

# export PYENV_VERSION=miniconda3-4.3.30
# python setup.py build
# python setup.py install
# pip install mysql-connector-python pyperf
# python bench_mariadb.py -o mariadb_bench_miniconda3_4_3_30.json --inherit-environ=TEST_USER,TEST_HOST,TEST_PORT
# python bench_mysql.py -o mysql_bench_miniconda3_4_3_30.json --inherit-environ=TEST_USER,TEST_HOST,TEST_PORT

# python -m pyperf compare_to mysql_bench_miniconda3_4_3_30.json mariadb_bench_miniconda3_4_3_30.json --table

#  export PYENV_VERSION=pypy2.6-7.2.0
# python setup.py build
# python setup.py install
# pip install mysql-connector-python pyperf
# cd testing
# export TEST_MODULE=mariadb
# python bench.py -o mariadb_bench_pypy3_6.json --inherit-environ=TEST_USER,TEST_HOST,TEST_PORT
# export TEST_MODULE=mysql.connector
# python bench.py -o mysql_bench_pypy3_6.json --inherit-environ=TEST_USER,TEST_HOST,TEST_PORT
# python -m pyperf compare_to mysql_bench_pypy3_6.json mariadb_bench_pypy3_6.json --table
# cd ..

# python -m pyperf compare_to mysql_bench.json mariadb_bench.json mysql_bench_pypy3_6.json mariadb_bench_pypy3_6.json \
#   mysql_bench_miniconda3_4_3_30.json mariadb_bench_miniconda3_4_3_30.json --table
else
  pyenv install $PYTHON_VER
  export PYENV_VERSION=$PYTHON_VER

  python setup.py build
  python setup.py install
  cd testing

  python -m unittest discover -v
  cd ..
fi



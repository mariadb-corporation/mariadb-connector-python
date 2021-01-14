#!/bin/bash

set -x
set -e

###################################################################################################################
# test different type of configuration
###################################################################################################################

if [ -n "$SKYSQL" ] || [ -n "$SKYSQL_HA" ]; then
  if [ -n "$SKYSQL" ]; then
    ###################################################################################################################
    # test SKYSQL
    ###################################################################################################################
    if [ -z "$SKYSQL_HOST" ] ; then
      echo "No SkySQL configuration found !"
      exit 0
    fi

    export TEST_USER=$SKYSQL_USER
    export TEST_HOST=$SKYSQL_HOST
    export TEST_PASSWORD=$SKYSQL_PASSWORD
    export TEST_PORT=$SKYSQL_PORT
    export TEST_DATABASE=testp

  else

    ###################################################################################################################
    # test SKYSQL with replication
    ###################################################################################################################
    if [ -z "$SKYSQL_HA" ] ; then
      echo "No SkySQL HA configuration found !"
      exit 0
    fi

    export TEST_USER=$SKYSQL_HA_USER
    export TEST_HOST=$SKYSQL_HA_HOST
    export TEST_PASSWORD=$SKYSQL_HA_PASSWORD
    export TEST_PORT=$SKYSQL_HA_PORT
    export TEST_DATABASE=testp
  fi

else

  export COMPOSE_FILE=.travis/docker-compose.yml
  export ENTRYPOINT=$PROJ_PATH/.travis/sql
  export ENTRYPOINT_PAM=$PROJ_PATH/.travis/pam

  export TEST_HOST=mariadb.example.com
  export TEST_DATABASE=testp
  export TEST_USER=bob
  export TEST_PORT=3305

  if [ -n "$MAXSCALE_VERSION" ] ; then
      # maxscale ports:
      # - non ssl: 4006
      # - ssl: 4009
      export TEST_PORT=4006
      export TEST_SSL_PORT=4009
      export COMPOSE_FILE=.travis/maxscale-compose.yml
      docker-compose -f ${COMPOSE_FILE} build
  fi

  mysql=( mysql --protocol=TCP -u${TEST_USER} -h${TEST_HOST} --port=${TEST_PORT} ${TEST_DATABASE})

  ###################################################################################################################
  # launch docker server and maxscale
  ###################################################################################################################
  docker-compose -f ${COMPOSE_FILE} up -d

  ###################################################################################################################
  # wait for docker initialisation
  ###################################################################################################################

  for i in {30..0}; do
    if echo 'SELECT 1' | "${mysql[@]}" &> /dev/null; then
        break
    fi
    echo 'data server still not active'
    sleep 2
  done

  if [ "$i" = 0 ]; then
    if echo 'SELECT 1' | "${mysql[@]}" ; then
        break
    fi

    docker-compose -f ${COMPOSE_FILE} logs
    if [ -n "$MAXSCALE_VERSION" ] ; then
        docker-compose -f ${COMPOSE_FILE} exec maxscale tail -n 500 /var/log/maxscale/maxscale.log
    fi
    echo >&2 'data server init process failed.'
    exit 1
  fi

  if [[ "$DB" != mysql* ]] ; then
    ###################################################################################################################
    # execute pam
    ###################################################################################################################
    docker-compose -f ${COMPOSE_FILE} exec -u root db bash /pam/pam.sh
    sleep 1
    docker-compose -f ${COMPOSE_FILE} restart db
    sleep 5

    ###################################################################################################################
    # wait for restart
    ###################################################################################################################

    for i in {30..0}; do
      if echo 'SELECT 1' | "${mysql[@]}" &> /dev/null; then
          break
      fi
      echo 'data server restart still not active'
      sleep 2
    done

    if [ "$i" = 0 ]; then
      if echo 'SELECT 1' | "${mysql[@]}" ; then
          break
      fi

      docker-compose -f ${COMPOSE_FILE} logs
      if [ -n "$MAXSCALE_VERSION" ] ; then
          docker-compose -f ${COMPOSE_FILE} exec maxscale tail -n 500 /var/log/maxscale/maxscale.log
      fi
      echo >&2 'data server restart process failed.'
      exit 1
    fi
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



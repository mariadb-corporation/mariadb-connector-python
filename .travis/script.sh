#!/bin/bash

set -x
set -e

###################################################################################################################
# test different type of configuration
###################################################################################################################
mysql=( mysql --protocol=tcp -ubob -h127.0.0.1 --port=3305 )

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

python -m unittest discover -v


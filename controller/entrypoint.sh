#!/bin/sh
set -e

echo "Waiting for MySQL at $MYSQL_HOST:$MYSQL_PORT..."
until nc -z -v -w30 $MYSQL_HOST $MYSQL_PORT
do
  echo "Waiting for database connection..."
  sleep 3
done

echo "MySQL is up - starting collector"
exec python collector.py
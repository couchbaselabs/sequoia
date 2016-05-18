#!/bin/sh
HOST=$1
Q=$2
if [ -n "$3" ]; then
  seq 1 $3 | xargs -I '{}'  curl -s $1/query/service -d "statement=$2"
else
  while [ 1 ] ; do
    curl -s $1/query/service -d "statement=$2"
  done
fi


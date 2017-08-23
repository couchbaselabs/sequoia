#!/bin/sh
HOST=$1
Q=$2
while [ 1 ] ; do
  curl -s $HOST/query/service -d "statement=$Q" -u Administrator:password > logs.txt
done


#!/bin/sh
HOST=$1
BUCKET=$2
DDOC=$3
VIEW=$4
PARAMS=$5
AUTH=${6:-Administrator:password}

URL=$HOST/$BUCKET/_design/$DDOC/_view/$VIEW?$PARAMS 
echo $URL
while [ 1 ] ; do
  curl -s -u $AUTH $URL > logs.txt
done

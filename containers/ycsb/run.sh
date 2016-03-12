#!/bin/bash

Url=$1
Site=http://$Url/query/service
while read line; do
  sql=$line
  echo curl -u Administrator:password -v $Site  -d statement="$sql"
  curl -u Administrator:password -v $Site  -d statement="$sql"
done < $2
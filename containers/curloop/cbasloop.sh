#!/bin/sh
#ID=`docker ps -a | grep "Up" | grep "sequoiatools/cbas" | awk '{print $1}'`
#HOST=`docker inspect --format '{{ .NetworkSettings.IPAddress }}' $ID`
HOST="172.17.0.4"
STATEMENT=$1
while [ 1 ] ; do
  curl -s --data pretty=true --data format=CLEAN_JSON --data-urlencode "statement=$STATEMENT" http://$HOST:8095/analytics/service -v #> logs.txt
done

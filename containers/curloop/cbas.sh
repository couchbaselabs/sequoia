#!/bin/sh
#ID=`docker ps -a | grep "Up" | grep "sequoiatools/cbas" | awk '{print $1}'`
#HOST=`docker inspect --format '{{ .NetworkSettings.IPAddress }}' $ID`
HOST="172.17.0.4"
STATEMENT=$@
STATEMENT=${STATEMENT//\\/""}  # remove \ slashes
echo "curl -s --data pretty=true --data format=CLEAN_JSON --data-urlencode \"statement=$STATEMENT\" http://$HOST:8095/analytics/service -v"
curl -s --data pretty=true --data format=CLEAN_JSON --data-urlencode "statement=$STATEMENT" http://$HOST:8095/analytics/service -v # > log
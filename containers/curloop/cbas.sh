#!/bin/sh
#ID=`docker ps -a | grep "Up" | grep "sequoiatools/cbas" | awk '{print $1}'`
#HOST=`docker inspect --format '{{ .NetworkSettings.IPAddress }}' $ID`
HOST="172.17.0.4"
STATEMENT=${@}
#echo $ID
echo $HOST
echo $STATEMENT
curl -s --data pretty=true --data format=CLEAN_JSON --data-urlencode "statement=$STATEMENT" http://$HOST:8095/analytics/service -v > logs.txt

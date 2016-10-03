#!/bin/sh
ID="`docker ps -a | grep "Up" | grep "ubuntu_cbas" | awk '{print $1}'`"
HOST=`docker inspect --format '{{ .NetworkSettings.IPAddress }}' $ID`
STATEMENT=$1
echo $ID
echo $HOST
echo $STATEMENT
curl -s --data pretty=true --data format=CLEAN_JSON --data-urlencode '$STATEMENT' http://$HOST:8095/analytics/service -v > logs.txt

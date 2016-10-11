#!/bin/sh
#ID=`docker ps -a | grep "Up" | grep "sequoiatools/cbas" | awk '{print $1}'`
#HOST=`docker inspect --format '{{ .NetworkSettings.IPAddress }}' $ID`
HOST="172.17.0.4"
STATEMENT=$@
STATEMENT=${STATEMENT//\\/""} # remove \ slashes
STATEMENT=${STATEMENT//\'NUM/""}  # to use nums in expression
while [ 1 ] ; do
    curl -s --data pretty=true --data-urlencode "statement=$STATEMENT" http://$HOST:8095/analytics/service > log
done

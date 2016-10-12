#!/bin/sh
#ID=`docker ps -a | grep "Up" | grep "sequoiatools/cbas" | awk '{print $1}'`
#HOST=`docker inspect --format '{{ .NetworkSettings.IPAddress }}' $ID`
HOST="172.17.0.5"  # we need run 'docker rm -fv $(docker ps -qa)' before test
STATEMENT=$@
STATEMENT=${STATEMENT//\\/""}  # remove \ slashes
STATEMENT=${STATEMENT//\'NUM/""}  # to use nums in expression
#echo "curl -s --data pretty=true --data-urlencode \"statement=$STATEMENT\" http://$HOST:8095/analytics/service -v"
curl -s --data pretty=true --data-urlencode "statement=$STATEMENT" http://$HOST:8095/analytics/service > log
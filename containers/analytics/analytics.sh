#!/bin/sh
HOST=$1
Q=$2
AUTH=$3

cmd="curl -s http://$HOST/analytics/service -d \"statement=$Q\" -u $AUTH --connect-timeout 60 -m 300"
echo $cmd>logs.txt
eval $cmd
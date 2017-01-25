#!/bin/bash

DIR=$1
ARGS=$2

echo $ARGS > /log/dcp-data.log
cd /sdk-data/workload/$DIR

tail -F /log/dcp-data.log &
mvn exec:java -DskipTests=true -Dmaven.repo.local=/tmp -Dexec.args="$DIR $ARGS"

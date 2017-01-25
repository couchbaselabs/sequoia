#!/bin/bash

DIR=$1
ARGS=$2
CLASS=$3

mkdir -p /work/`hostname`
echo $ARGS, $CLASS > /log/dcp-data.log
cd /sdk-data/client/$DIR

tail -F /log/dcp-data.log &
mvn exec:java -DskipTests=true -Dmaven.repo.local=/tmp -Dexec.args="$DIR $CLASS $ARGS" -Dexec.mainClass=$CLASS

#!/bin/sh

DURATION=$1
RATE=$2
REST=$3
URL=$4
REQUEST=$(echo $* | cut -d' ' -f5-)

echo "REQUEST", $REQUEST
echo "========="
echo $REQUEST > request.txt;
echo $REST $URL | vegeta attack -duration=$DURATION -rate=$RATE -body=request.txt > results.bin
vegeta report -inputs=results.bin  >  results.txt
vegeta report -inputs=results.bin -reporter=plot > plot.html

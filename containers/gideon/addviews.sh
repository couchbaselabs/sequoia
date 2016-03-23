#!/bin/bash

HOST=$1 #include port ie..172.23.106.14:8092
BUCKET=$2
DDOC=${3:-scale}
AUTH=${4:-Administrator:password}
echo curl -X PUT -u $AUTH -H "'Content-Type:application/json'" http://$HOST/$BUCKET/_design/$DDOC -d@views.json
cat views.json
curl -X PUT -u $AUTH -H 'Content-Type:application/json' http://$HOST/$BUCKET/_design/$DDOC -d@views.json

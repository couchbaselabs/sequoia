#!/bin/bash

COUCHBASE_SERVER_URL=$1
MODE=$2
SYNC_GATEWAY_CONFIG=/home/sync_gateway/sync_gateway.json

echo "Using CBS: ${COUCHBASE_SERVER_URL} Mode: ${MODE}"

# Add cluster configuration property if you are running in distributed index mode (accels)
if [ "${MODE}" == "di" ]; then
    sed -i 's#CHANNEL_INDEX#"channel_index":{"server":"http://node0:8091","bucket":"index-bucket","username":"index-bucket","password": "password","writer":false},#' $SYNC_GATEWAY_CONFIG
else
    sed -i 's/CHANNEL_INDEX/"import_docs":"continuous",/' $SYNC_GATEWAY_CONFIG
fi

# Replace 'COUCHBASE_SERVER_URL in /etc/sync_gateway/config.json with Server IP
sed -i "s/\(node0\)\(.*\)/${COUCHBASE_SERVER_URL}\2/" $SYNC_GATEWAY_CONFIG

# start sync gateway
exec systemctl start sync_gateway

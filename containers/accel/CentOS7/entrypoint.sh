#!/bin/bash

COUCHBASE_SERVER_URL=$1
SYNC_GATEWAY_CONFIG=/home/sg_accel/sg_accel.json

echo "Using CBS: ${COUCHBASE_SERVER_URL}"

# Replace 'COUCHBASE_SERVER_URL in /etc/sync_gateway/config.json with Server IP
sed -i "s/\(node0\)\(.*\)/${COUCHBASE_SERVER_URL}\2/" $SYNC_GATEWAY_CONFIG

# start sg_accel
exec systemctl start sg_accel

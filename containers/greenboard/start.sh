#!/bin/bash

HOST=${1:-127.0.0.1}
LISTEN=${2:-127.0.0.1}
sed -i  "s/exports.Cluster.*/exports.Cluster='$HOST'/" config.js
sed -i  "s/exports.httpListen.*/exports.httpListen='$LISTEN'/" config.js 
node index.js

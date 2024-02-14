#!/bin/bash
var=1
j=$#;
while [ $var -le $j ]
do
#echo "Cbcollect - $var: $1";
curl --no-progress-meter $1 --output logbundle_$var.zip
unzip -q logbundle_$var.zip -d logbundle_$var
cd logbundle_$var
cd $(ls -d */|head -n 1)
#Projector
# set -x
zgrep -i "Menelaus-Auth-User:\[" ns_server.projector.log
zgrep -i "panic" ns_server.projector.log
zgrep -i "Error parsing XATTR" ns_server.projector.log
zgrep -i "Basic\s[a-zA-Z]\{10,\}" ns_server.projector.log
zgrep -i "seq order violation" ns_server.projector.log
#info.log
zgrep -i "failover exited with reason" ns_server.info.log   | grep -vE "exited with status 0"
zgrep -i "due to operation being unsafe for service index" ns_server.info.log   | grep -vE "exited with status 0"
zgrep -i "exited with status" ns_server.info.log   | grep -vE "exited with status 0"
zgrep -i "Basic\s[a-zA-Z]\{10,\}" ns_server.info.log   | grep -vE "exited with status 0"
zgrep -i "Menelaus-Auth-User:\[" ns_server.info.log   | grep -vE "exited with status 0"
#query
zgrep -i "panic" ns_server.query.log   | grep -vE "not available"
zgrep -i "fatal" ns_server.query.log   | grep -vE "not available"
zgrep -i "Encounter planner error" ns_server.query.log   | grep -vE "not available"
zgrep -i "Basic\s[a-zA-Z]\{10,\}" ns_server.query.log   | grep -vE "not available"
zgrep -i "Menelaus-Auth-User:\[" ns_server.query.log   | grep -vE "not available"
zgrep -i "invalid byte in chunk length" ns_server.query.log   | grep -vE "not available"
#error.log
zgrep -i "rebalance exited" ns_server.error.log
zgrep -i "failover exited with reason" ns_server.error.log
zgrep -i "Basic\s[a-zA-Z]\{10,\}" ns_server.error.log
zgrep -i "Menelaus-Auth-User:\[" ns_server.error.log
zgrep -i "Join completion call failed" ns_server.error.log
#indexer.log
zgrep -i "Internal error while creating new scan request" ns_server.indexer.log   | grep -vE "fatal remote"
zgrep -i "invalid length of composite element" ns_server.indexer.log   | grep -vE "fatal remote"
#zgrep -i "TS falls out of snapshot boundary" ns_server.indexer.log   | grep -vE "fatal remote"
zgrep -i "ensureMonotonicTs  Align seqno smaller than lastFlushTs" ns_server.indexer.log   | grep -vE "fatal remote"
zgrep -i "Storage corrupted and unrecoverable" ns_server.indexer.log   | grep -vE "fatal remote"
zgrep -i "invalid last page" ns_server.indexer.log   | grep -vE "fatal remote"
zgrep -i "found missing page" ns_server.indexer.log   | grep -vE "fatal remote"
zgrep -i "Menelaus-Auth-User:\[" ns_server.indexer.log   | grep -vE "fatal remote"
zgrep -i "Basic\s[a-zA-Z]\{10,\}" ns_server.indexer.log   | grep -vE "fatal remote"
zgrep -i "processFlushAbort" ns_server.indexer.log   | grep -vE "fatal remote"
zgrep -i "corruption" ns_server.indexer.log   | grep -vE "fatal remote"
zgrep -i "Encounter planner error" ns_server.indexer.log   | grep -vE "fatal remote"
zgrep -i "protobuf.Error" ns_server.indexer.log   | grep -vE "fatal remote"
zgrep -i "Error parsing XATTR" ns_server.indexer.log   | grep -vE "fatal remote"
zgrep -i "panic" ns_server.indexer.log   | grep -vE "fatal remote"
zgrep -i "fatal" ns_server.indexer.log   | grep -vE "fatal remote"
zgrep -i "\[ERRO\]\[FDB\]" ns_server.indexer.log   | grep -vE "fatal remote"
zgrep -i "zero" ns_server.indexer.log   | grep -vE "fatal remote"
zgrep -i "ReplicaViolation" ns_server.indexer.log   | grep -vE "fatal remote"
zgrep -i "ExcludeNodeViolation" ns_server.indexer.log   | grep -vE "fatal remote"
zgrep -i "EquivIndexViolation" ns_server.indexer.log   | grep -vE "fatal remote"
zgrep -i "ServerGroupViolation" ns_server.indexer.log   | grep -vE "fatal remote"
zgrep -i "DeleteNodeViolation" ns_server.indexer.log   | grep -vE "fatal remote"
zgrep -i "NoViolation" ns_server.indexer.log   | grep -vE "fatal remote"
zgrep -i "MemoryViolation" ns_server.indexer.log   | grep -vE "fatal remote"
zgrep -i "StorageMgr::handleCreateSnapshot Disk commit timestamp is not snapshot aligned" ns_server.indexer.log   | grep -vE "fatal remote"
#memcached.log
zgrep -i "CRITICAL" memcached.log
zgrep -i "Basic\s[a-zA-Z]\{10,\}" memcached.log
zgrep -i "Menelaus-Auth-User:\[" memcached.log
zgrep -i "exception occurred in runloop" memcached.log
zgrep -i "exception occurred in runloop" ns_server.babysitter.log
zgrep -i "failover exited with reason" ns_server.babysitter.log
zgrep -i "Basic\s[a-zA-Z]\{10,\}" ns_server.babysitter.log
zgrep -i "Menelaus-Auth-User:\[" ns_server.babysitter.log
# set +x
var=$((var+1))
shift 1
cd ../..
done
rm -rf log*
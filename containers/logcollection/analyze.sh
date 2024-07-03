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
zgrep --text -i "Menelaus-Auth-User:\[" ns_server.projector.log
zgrep --text -i "panic" ns_server.projector.log
zgrep --text -i "Error parsing XATTR" ns_server.projector.log
zgrep --text -i "Basic\s[a-zA-Z]\{10,\}" ns_server.projector.log
zgrep --text -i "seq order violation" ns_server.projector.log
#info.log
zgrep --text -i "failover exited with reason" ns_server.info.log   | grep --text -vE "exited with status 0"
zgrep --text -i "due to operation being unsafe for service index" ns_server.info.log   | grep --text -vE "exited with status 0"
zgrep --text -i "exited with status" ns_server.info.log   | grep --text -vE "exited with status 0"
zgrep --text -i "Basic\s[a-zA-Z]\{10,\}" ns_server.info.log   | grep --text -vE "exited with status 0"
zgrep --text -i "Menelaus-Auth-User:\[" ns_server.info.log   | grep --text -vE "exited with status 0"
#query
zgrep --text -i "panic" ns_server.query.log   | grep --text -vE "not available"
zgrep --text -i "fatal" ns_server.query.log   | grep --text -vE "not available"
zgrep --text -i "Encounter planner error" ns_server.query.log   | grep --text -vE "not available"
zgrep --text -i "Basic\s[a-zA-Z]\{10,\}" ns_server.query.log   | grep --text -vE "not available"
zgrep --text -i "Menelaus-Auth-User:\[" ns_server.query.log   | grep --text -vE "not available"
zgrep --text -i "invalid byte in chunk length" ns_server.query.log   | grep --text -vE "not available"
#error.log
zgrep --text -i "rebalance exited" ns_server.error.log
zgrep --text -i "failover exited with reason" ns_server.error.log
zgrep --text -i "Basic\s[a-zA-Z]\{10,\}" ns_server.error.log
zgrep --text -i "Menelaus-Auth-User:\[" ns_server.error.log
zgrep --text -i "Join completion call failed" ns_server.error.log
#indexer.log
zgrep --text -i "Internal error while creating new scan request" ns_server.indexer.log   | grep --text -vE "fatal remote"
zgrep --text -i "invalid length of composite element" ns_server.indexer.log   | grep --text -vE "fatal remote"
#zgrep --text -i "TS falls out of snapshot boundary" ns_server.indexer.log   | grep --text -vE "fatal remote"
zgrep --text -i "ensureMonotonicTs  Align seqno smaller than lastFlushTs" ns_server.indexer.log   | grep --text -vE "fatal remote"
zgrep --text -i "Storage corrupted and unrecoverable" ns_server.indexer.log   | grep --text -vE "fatal remote"
zgrep --text -i "invalid last page" ns_server.indexer.log   | grep --text -vE "fatal remote"
zgrep --text -i "found missing page" ns_server.indexer.log   | grep --text -vE "fatal remote"
zgrep --text -i "Menelaus-Auth-User:\[" ns_server.indexer.log   | grep --text -vE "fatal remote"
zgrep --text -i "Basic\s[a-zA-Z]\{10,\}" ns_server.indexer.log   | grep --text -vE "fatal remote"
zgrep --text -i "processFlushAbort" ns_server.indexer.log   | grep --text -vE "fatal remote"
zgrep --text -i "corruption" ns_server.indexer.log   | grep --text -vE "fatal remote"
zgrep --text -i "Encounter planner error" ns_server.indexer.log   | grep --text -vE "fatal remote"
zgrep --text -i "protobuf.Error" ns_server.indexer.log   | grep --text -vE "fatal remote"
zgrep --text -i "Error parsing XATTR" ns_server.indexer.log   | grep --text -vE "fatal remote"
zgrep --text -i "panic" ns_server.indexer.log   | grep --text -vE "fatal remote"
zgrep --text -i "fatal" ns_server.indexer.log   | grep --text -vE "fatal remote"
zgrep --text -i "\[ERRO\]\[FDB\]" ns_server.indexer.log   | grep --text -vE "fatal remote"
zgrep --text -i "zero" ns_server.indexer.log   | grep --text -vE "fatal remote"
zgrep --text -i "ReplicaViolation" ns_server.indexer.log   | grep --text -vE "fatal remote"
zgrep --text -i "ExcludeNodeViolation" ns_server.indexer.log   | grep --text -vE "fatal remote"
zgrep --text -i "EquivIndexViolation" ns_server.indexer.log   | grep --text -vE "fatal remote"
zgrep --text -i "ServerGroupViolation" ns_server.indexer.log   | grep --text -vE "fatal remote"
zgrep --text -i "DeleteNodeViolation" ns_server.indexer.log   | grep --text -vE "fatal remote"
zgrep --text -i "NoViolation" ns_server.indexer.log   | grep --text -vE "fatal remote"
zgrep --text -i "MemoryViolation" ns_server.indexer.log   | grep --text -vE "fatal remote"
zgrep --text -i "StorageMgr::handleCreateSnapshot Disk commit timestamp is not snapshot aligned" ns_server.indexer.log   | grep --text -vE "fatal remote"
#memcached.log
zgrep --text -i "CRITICAL" memcached.log
zgrep --text -i "Basic\s[a-zA-Z]\{10,\}" memcached.log
zgrep --text -i "Menelaus-Auth-User:\[" memcached.log
zgrep --text -i "exception occurred in runloop" memcached.log
zgrep --text -i "exception occurred in runloop" ns_server.babysitter.log
zgrep --text -i "failover exited with reason" ns_server.babysitter.log
zgrep --text -i "Basic\s[a-zA-Z]\{10,\}" ns_server.babysitter.log
zgrep --text -i "Menelaus-Auth-User:\[" ns_server.babysitter.log
#analytics
zgrep --text -i "fata" ns_server.analytics_error* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "fata" ns_server.analytics_info* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "Analytics Service is temporarily unavailable" ns_server.analytics_error* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "Analytics Service is temporarily unavailable" ns_server.analytics_info* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "Failed during startup task" ns_server.analytics_error* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "Failed during startup task" ns_server.analytics_info* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text  "HYR0" ns_server.analytics_error* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text  "HYR0" ns_server.analytics_info* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text  "ASX" ns_server.analytics_error* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text  "ASX" ns_server.analytics_info* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "IllegalStateException" ns_server.analytics_error* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "IllegalStateException" ns_server.analytics_info* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'


zgrep --text -i "ACIDException" ns_server.analytics_error* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "ACIDException" ns_server.analytics_info* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "MetadataException" ns_server.analytics_error* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "MetadataException" ns_server.analytics_info* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "OverflowException" ns_server.analytics_error* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "OverflowException" ns_server.analytics_info* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "UnderflowException" ns_server.analytics_error* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "UnderflowException" ns_server.analytics_info* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "NullPointerException" ns_server.analytics_error* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "NullPointerException" ns_server.analytics_info* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "StackOverflowException" ns_server.analytics_error* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "StackOverflowException" ns_server.analytics_info* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "Failure closing a closeable resource" ns_server.analytics_error* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "Failure closing a closeable resource" ns_server.analytics_info* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'


zgrep --text -i "Basic\s[a-zA-Z]\{10,\}" ns_server.analytics_error* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "Basic\s[a-zA-Z]\{10,\}" ns_server.analytics_info* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "Menelaus-Auth-User:\[" ns_server.analytics_error* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "Menelaus-Auth-User:\[" ns_server.analytics_info* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "panic" ns_server.analytics_error* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "panic" ns_server.analytics_info* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "LEAK: ByteBuf.release() was not called" ns_server.analytics_error* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "LEAK: ByteBuf.release() was not called" ns_server.analytics_info* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "failed to migrate metadata partition" ns_server.analytics_error* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "failed to migrate metadata partition" ns_server.analytics_info* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "Internal error" ns_server.analytics_error* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "Internal error" ns_server.analytics_info* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "CBAS\[number\]" ns_server.analytics_error* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "CBAS\[number\]" ns_server.analytics_info* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "IllegalReferenceCountException" ns_server.analytics_error* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "IllegalReferenceCountException" ns_server.analytics_info* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "ArrayIndexOutOfBoundsException" ns_server.analytics_error* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "ArrayIndexOutOfBoundsException" ns_server.analytics_info* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "java.lang.OutOfMemoryError" ns_server.analytics_info* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'
zgrep --text -i "java.lang.OutOfMemoryError" ns_server.analytics_error* | grep --text -vE '(HYR0010|HYR0115|ASX3110|HYR0114)'

# set +x
var=$((var+1))
shift 1
cd ../..
done
rm -rf log*
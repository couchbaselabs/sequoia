#!/bin/sh

record_count=$1
num_threads=$2
hostname=$3
bucket_name=$4

service memcached start

cd /YCSB

cmd="nohup bin/ycsb load couchbase2 -P workloads/soe/workloadsmix3 -p writeallfields=true -threads $num_threads -p target=0 -p fieldlength=100 -p fieldcount=10 -p couchbase.host=$hostname -p couchbase.bucket=$bucket_name -p couchbase.upsert=true -p couchbase.epoll=true -p couchbase.boost=48 -p couchbase.kvEndpoints=1 -p couchbase.sslMode=none -p couchbase.certKeystoreFile=../certificates/data.keystore -p couchbase.certKeystorePassword=storepass -p couchbase.password=password -p exportfile=ycsb_run_3.log -p couchbase.persistTo=0 -p couchbase.replicateTo=0  -p operationcount=500000000 -p totalrecordcount=$record_count  -p recordcount=$record_count -p insertstart=400 < /dev/null > /dev/null &"
echo $cmd
eval $cmd
cmd="bin/ycsb run couchbase2 -P workloads/soe/workloadsmix3 -p writeallfields=true -threads $num_threads -p target=0 -p fieldlength=100 -p fieldcount=10 -p couchbase.host=$hostname -p couchbase.bucket=$bucket_name -p couchbase.upsert=true -p couchbase.epoll=true -p couchbase.boost=48 -p couchbase.kvEndpoints=1 -p couchbase.sslMode=none -p couchbase.certKeystoreFile=../certificates/data.keystore -p couchbase.certKeystorePassword=storepass -p couchbase.password=password -p exportfile=ycsb_run_3.log -p couchbase.persistTo=0 -p couchbase.replicateTo=0  -p operationcount=500000000 -p totalrecordcount=$record_count  -p recordcount=$record_count -p insertstart=400 < /dev/null > /dev/null"
echo $cmd
eval $cmd

#!/bin/bash

HOST=$1
BUCKET=$2
NUMDOCS=$3

RANDOM=$$

while [ 1 ] ; do
	for i in `seq $3`
	do
		doc_id=$RANDOM
		echo java -cp transaction-performer.jar com.couchbase.transaction clusterIp=$1 operationDocids=insert-test$doc_id,read-test$doc_id,replace-test$doc_id,read-test$doc_id bucket=$2
		java -cp transaction-performer.jar com.couchbase.transaction clusterIp=$1 operationDocids=insert-test$doc_id,read-test$doc_id,replace-test$doc_id,read-test$doc_id bucket=$2
	done
        sleep 2h
done

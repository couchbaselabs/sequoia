#!/bin/bash
set -e
cp ~/S3Creds_tmp .

git clone git@github.com:couchbase/sdkd-java.git || true
git clone -b for_docker git@github.com:couchbaselabs/sdkdclient-ng.git || true

docker build -t sequoiatools/sdk .

export CONTAINER_NAME=sdkdclient
~/bin/sequoia sdk -expose_ports -command "-I spock-basic.ini --install-skip true --rebound 90 --bucket-password="password" --testsuite-test=Rb1Swap --testsuite-variants=HYBRID -d all:debug -A S3Creds_tmp -C share/rexec --rexec_path=/root/sdkd-java/run-sdkd-java --rexec_port=8050" -container_name ${CONTAINER_NAME}

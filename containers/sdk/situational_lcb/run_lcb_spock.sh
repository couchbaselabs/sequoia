#!/bin/bash
set -e
cp ~/S3Creds_tmp .

rm -rf sdkd-cpp
rm -rf sdkdclient-ng
git clone git@github.com:couchbase/sdkd-cpp.git
git clone -b for_docker git@github.com:couchbaselabs/sdkdclient-ng.git

docker build -t sequoiatools/sdk .
export CONTAINER_NAME=sdkdclient
~/bin/sequoia sdk -expose_ports -command "-I spock-basic.ini --install-skip true --rebound 90 --bucket-password="password" --testsuite-test=Rb1Swap --testsuite-variants=HYBRID -d all:debug -A S3Creds_tmp -C share/rexec --rexec_path=/root/sdkd-cpp/sdkd_lcb --rexec_port=8050 --exec_arg=-l 8050 --rexec_arg=-L log.txt" -container_name ${CONTAINER_NAME}


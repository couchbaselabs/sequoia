#!/bin/bash
set -e

SDK_COMMIT=${1:-master}
CORE_COMMIT=${2:-master}



# checkout java sdk
git clone git://github.com/couchbase/couchbase-jvm-core.git
(cd couchbase-jvm-core && git checkout ${CORE_COMMIT} && git log -n 2)
git clone git://github.com/couchbase/couchbase-java-client.git
(cd couchbase-java-client && git checkout ${SDK_COMMIT} && git log -n 2)

# build sdkd
cp sdkd-java/util/buildSDKDJar.sh .
./buildSDKDJar.sh

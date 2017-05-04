#!/bin/bash

SDK=${1:-lcb}
SDK_COMMIT=${2:-master}
SDKD_COMMIT=${3:-master}
SDKDCLIENT_COMMIT=${4:-for_docker}
CORE_COMMIT=${5:-master}

echo SDK=${SDK}, SDK_COMMIT=${SDK_COMMIT}, SDKD_COMMIT=${SDKD_COMMIT}, SDKDCLIENT_COMMIT=${SDKDCLIENT_COMMIT}, CORE_COMMIT=${CORE_COMMIT}
# checkout sdkd
(cd ${SDK} && ./checkout.sh ${SDKD_COMMIT})

# checkout sdkdclient
(rm -rf sdkdclient-ng && git clone git@github.com:couchbaselabs/sdkdclient-ng.git && cd sdkdclient-ng && git checkout ${SDKDCLIENT_COMMIT})

docker build \
	--build-arg SDK=${SDK} \
	--build-arg SDK_COMMIT=${SDK_COMMIT} \
	--build-arg CORE_COMMIT=${CORE_COMMIT} \
	-t sequoiatools/sdk:latest .

export CONTAINER_NAME=sdkdclient

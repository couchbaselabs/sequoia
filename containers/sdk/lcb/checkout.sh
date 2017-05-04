#!/bin/bash

SDKD_COMMIT=${1:-master}

rm -rf sdkd-cpp
git clone git@github.com:couchbase/sdkd-cpp.git
(cd sdkd-cpp && git checkout ${SDKD_COMMIT})


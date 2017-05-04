#!/bin/bash

SDKD_COMMIT=${1:-master}

rm -rf sdkd-java
git clone git@github.com:couchbase/sdkd-java.git
(cd sdkd-java && git checkout ${SDKD_COMMIT})


#!/bin/bash
set -e

SDK_COMMIT=${1:-master}

# build libcouchbase
git clone git://github.com/couchbase/libcouchbase.git
cd libcouchbase
git checkout ${SDK_COMMIT}
cmake -DCMAKE_INSTALL_PREFIX=/root/libcouchbase/inst -DLCB_NO_SSL=0 -DCMAKE_BUILD_TYPE=Debug ./
make
make install

# build sdkd
cd ../sdkd-cpp
git submodule init
git submodule update
(cd src/contrib/json-cpp && python amalgamate.py)
cmake -DLCB_ROOT=/root/libcouchbase/inst -DCMAKE_BUILD_TYPE=DEBUG ./
make

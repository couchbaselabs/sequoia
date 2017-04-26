FROM centos:7

# NOTE building this container requires access to sdk repo
# the following folders should be cloned before doing a build here
#  * git@github.com:couchbaselabs/sdkdclient-ng.git
#  * git@github.com:couchbase/sdkd-cpp.git

# enviornment
RUN yum update -y; yum install -y java-1.8.0-openjdk-devel maven git gcc make cmake
RUN yum install -y gcc-c++.x86_64
RUN yum install -y libev libevent libev-devel libevent-devel openssl-devel
WORKDIR /root

# build libcouchbase
RUN git clone git://github.com/couchbase/libcouchbase.git
WORKDIR libcouchbase
RUN  git checkout 2.6.2
RUN cmake -DCMAKE_INSTALL_PREFIX=/root/libcouchbase/inst -DLCB_NO_SSL=0 -DCMAKE_BUILD_TYPE=Debug ./
RUN make -j 8
RUN make install

# install sdkd
WORKDIR /root
ADD sdkd-cpp /root/sdkd-cpp
WORKDIR /root/sdkd-cpp
WORKDIR src/contrib/json-cpp
RUN python amalgamate.py
WORKDIR /root/sdkd-cpp
RUN cmake -DLCB_ROOT=/root/libcouchbase/inst -DCMAKE_BUILD_TYPE=DEBUG ./
RUN  make -j 8
WORKDIR /root
ADD sdkdclient-ng /root/sdkdclient-ng

# install sdkdclient
WORKDIR /root/sdkdclient-ng
RUN mvn package -Dmaven.test.skip=true
ENV BRUN_PERCENTILE=85
#RUN mapfile -c 1 -C subst
RUN mkdir -p pylib
RUN cp /root/sdkd-cpp/pylib/s3upload.py pylib/s3upload.py
COPY brun brun
COPY host2ip.sh host2ip.sh

# add runtime ini-files
COPY watson-basic.ini watson-basic.ini
RUN sed -i 's/num_containers.*//' watson-basic.ini
ENTRYPOINT ["./brun"]

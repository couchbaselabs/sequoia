FROM ubuntu:16.04

WORKDIR /root

RUN apt-get update && apt-get -y install gcc g++ make cmake git-core git-core libevent-dev

RUN git clone git://github.com/couchbase/libcouchbase.git && \
    mkdir libcouchbase/build

WORKDIR libcouchbase/build
RUN ../cmake/configure --prefix=/usr --disable-tests && \
      make && \
      make install

WORKDIR bin
ENTRYPOINT ["cbc-pillowfight"]

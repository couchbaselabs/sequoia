FROM ubuntu:14.04

WORKDIR /root

# sys deps
RUN apt-get update && \
    apt-get install -y gcc g++ make cmake git-core libevent-dev libev-dev

RUN git clone git://github.com/couchbase/libcouchbase.git && \
    mkdir libcouchbase/build

WORKDIR libcouchbase/build
RUN ../cmake/configure --prefix=/usr && \
      make && \
      make install

WORKDIR bin
ENTRYPOINT ["cbc-pillowfight"]

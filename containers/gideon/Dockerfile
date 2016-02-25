FROM ubuntu:14.04

WORKDIR /root

# sys deps
RUN apt-get update && \
    apt-get install -y gcc g++ make cmake git-core git-core python-dev python-pip libevent-dev libev-dev

# python deps
RUN pip install gevent

# sdk
RUN git clone git://github.com/couchbase/libcouchbase.git && \
    mkdir libcouchbase/build

WORKDIR libcouchbase/build
RUN ../cmake/configure --prefix=/usr && \
      make && \
      make install
WORKDIR /root
RUN pip install git+git://github.com/couchbase/couchbase-python-client &&\
    pip install pyyaml && \
    pip install eventlet

# src
RUN git clone https://github.com/couchbaselabs/gideon.git
WORKDIR gideon

COPY spec.yaml /spec.yaml
CMD python gideon.py kv --spec /spec.yaml

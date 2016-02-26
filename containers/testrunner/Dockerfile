FROM ubuntu:14.04

WORKDIR /root

# sys deps
RUN apt-get update && \
    apt-get install -y gcc g++ make cmake git-core git-core python-dev python-pip libevent-dev libev-dev

# python deps
RUN pip install gevent paramiko boto

# sdk
RUN git clone git://github.com/couchbase/testrunner.git

WORKDIR testrunner 

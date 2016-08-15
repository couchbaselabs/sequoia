FROM ubuntu:14.04
RUN apt-get update
RUN apt-get install -y gcc g++ make cmake git-core libevent-dev libev-dev libssl-dev libffi-dev psmisc iptables zip unzip python-dev python-pip 

# build libcouchbase
RUN git clone git://github.com/couchbase/libcouchbase.git && \
    mkdir libcouchbase/build

WORKDIR libcouchbase/build
RUN ../cmake/configure --prefix=/usr && \
      make && \
      make install

WORKDIR /
RUN git clone git://github.com/couchbase/testrunner.git
WORKDIR testrunner

# install python deps
RUN pip install paramiko &&\
    pip install gevent &&\
    pip install boto &&\
    pip install pyyaml &&\
    pip install couchbase

COPY local.ini local.ini
COPY upgrade_local.ini upgrade_local.ini
COPY host2ip.sh host2ip.sh
COPY testrunner testrunner
ENTRYPOINT ["./testrunner"]

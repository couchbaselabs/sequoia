FROM ubuntu:14.04
RUN apt-get update
RUN apt-get install -y wget lsb-release gcc g++ make cmake git-core libevent-dev libev-dev libssl-dev libffi-dev psmisc iptables zip unzip python-dev python-pip vim curl

# Install libcouchbase binary
RUN wget http://packages.couchbase.com/releases/couchbase-release/couchbase-release-1.0-6-amd64.deb
RUN dpkg -i couchbase-release-1.0-6-amd64.deb
RUN apt-get update
RUN apt-get install -y --allow-unauthenticated libcouchbase-dev libcouchbase2-bin build-essential


WORKDIR /
RUN git clone git://github.com/couchbase/testrunner.git
WORKDIR testrunner
ARG BRANCH=master
RUN git checkout $BRANCH
RUN git pull origin $BRANCH
RUN git fetch
RUN git reset --hard origin/$BRANCH

# install python deps
RUN pip2 install --upgrade packaging appdirs
RUN pip install -U pip setuptools
RUN pip install paramiko &&\
    pip install gevent &&\
    pip install boto &&\
    pip install httplib2 &&\
    pip install pyyaml &&\
    pip install couchbase &&\
    pip install Geohash &&\
    pip install pytz

COPY local.ini local.ini
COPY upgrade_local.ini upgrade_local.ini
COPY host2ip.sh host2ip.sh
COPY sync.sh sync.sh
COPY testrunner testrunner
COPY testrunner scripts/testrunner-docker
RUN cp testrunner scripts/testrunner-orig

# make sure tests use storage memory and avoid htp (for now)
RUN sed -i 's/IS_CONTAINER.*/IS_CONTAINER = True/' lib/testconstants.py
RUN sed -i 's/ALLOW_HTP.*/ALLOW_HTP=False/' lib/testconstants.py
RUN echo git pull origin $BRANCH > /tmp/.pull
RUN chmod +x /tmp/.pull
ENTRYPOINT ["./testrunner"]

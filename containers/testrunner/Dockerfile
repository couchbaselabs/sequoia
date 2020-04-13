FROM centos:7
RUN yum update -y
RUN yum install git wget make gcc bzip2 zlib-devel bzip2-devel openssl-devel ncurses-devel sqlite-devel readline-devel tk-devel gdbm-devel db4-devel libpcap-devel xz-devel readline-devel sqlite sqlite-devel libffi-devel gcc-c++ python-devel python-pip -y

WORKDIR /
RUN wget https://www.python.org/ftp/python/3.7.6/Python-3.7.6.tgz
RUN tar -xvf Python-3.7.6.tgz
WORKDIR Python-3.7.6
RUN ./configure --enable-optimizations
RUN make altinstall
RUN alternatives --install /usr/local/bin/python3 python3 /usr/local/bin/python3.7 1
RUN alternatives --install /usr/local/bin/pip3 pip3 /usr/local/bin/pip3.7 1
WORKDIR /
# Install libcouchbase binary
RUN wget http://packages.couchbase.com/releases/couchbase-release/couchbase-release-1.0-6-x86_64.rpm
RUN rpm -iv couchbase-release-1.0-6-x86_64.rpm
RUN yum install libcouchbase-devel libcouchbase2-bin gcc gcc-c++ libcouchbase2-libev libcouchbase2-libevent -y

RUN pip3 install couchbase sgmllib3k paramiko httplib2 pyyaml beautifulsoup4 Geohash python-geohash deepdiff pyes pytz requests jsonpickle docker

RUN git clone git://github.com/couchbase/testrunner.git
WORKDIR testrunner
ARG BRANCH=master
RUN git checkout $BRANCH
RUN git pull origin $BRANCH
RUN git fetch
RUN git reset --hard origin/$BRANCH

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

FROM centos:7

MAINTAINER Couchbase Docker Team <docker@couchbase.com>

# Update server
RUN yum -y update; yum clean all

# Install utils and dependencies
RUN yum install -y tar \
    && yum clean all && \
      yum -y install openssl \
      lsof lshw net-tools numactl \
      sysstat wget screen psmisc \
      zip unzip glibc glibc-devel

# Install python-httplib2
RUN curl https://bootstrap.pypa.io/get-pip.py | python - ; pip install httplib2

COPY functions /etc/init.d/

# Install gosu for startup script
RUN gpg --keyserver ha.pool.sks-keyservers.net --recv-keys B42F6819007F00F88E364FD4036A9C25BF357DD4 \
    && curl -o /usr/local/bin/gosu -sSL "https://github.com/tianon/gosu/releases/download/1.4/gosu-amd64" \
    && curl -o /usr/local/bin/gosu.asc -sSL "https://github.com/tianon/gosu/releases/download/1.4/gosu-amd64.asc" \
    && gpg --verify /usr/local/bin/gosu.asc \
    && rm /usr/local/bin/gosu.asc \
    && chmod +x /usr/local/bin/gosu

# Create Couchbase user with UID 1000 (necessary to match default
# boot2docker UID)
RUN groupadd -g1000 couchbase && \
    useradd couchbase -g couchbase -u1000 -m -s /bin/bash && \
    echo 'couchbase:couchbase' | chpasswd


ARG VERSION=4.6.0
ARG BUILD_NO=3552
ARG FLAVOR=watson
ARG BUILD_PKG=couchbase-server-enterprise-$VERSION-$BUILD_NO-centos7.x86_64.rpm
ARG BASE_URL=http://172.23.120.24/builds/latestbuilds/couchbase-server/$FLAVOR/$BUILD_NO

ARG BUILD_URL=$BASE_URL/$BUILD_PKG
RUN echo $BUILD_URL && \
    wget -N $BUILD_URL

# Install couchbase
RUN rpm --install $BUILD_PKG 

#clean the cache
RUN yum clean all


COPY scripts/couchbase-start /usr/local/bin/

LABEL Name=rhel7/couchbase-server
LABEL Release=Latest 
LABEL Vendor=Couchbase 
LABEL Version=4.5.1 
LABEL Architecture="x86_64"
LABEL RUN="docker run -d --rm --privileged -p 8091:8091 --restart always --name NAME IMAGE \
            -v /opt/couchbase/var:/opt/couchbase/var \
            -v /opt/couchbase/var/lib/moxi:/opt/couchbase/var/lib/moxi \
            -v /opt/couchbase/var/lib/stats:/opt/couchbase/var/lib/stats "


ENV PATH=$PATH:/opt/couchbase/bin:/opt/couchbase/bin/tools:/opt/couchbase/bin/install
ENTRYPOINT ["couchbase-start"]
CMD ["couchbase-server", "--", "-noinput"]
# pass -noinput so it doesn't drop us in the erlang shell

EXPOSE 8091 8092 8093 11207 11210 11211 18091 18092
#VOLUME /opt/couchbase/var

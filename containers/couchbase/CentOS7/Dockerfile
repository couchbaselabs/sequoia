FROM centos/systemd

MAINTAINER Couchbase Docker Team <docker@couchbase.com>

# Update server
RUN yum -y update; yum clean all

# Install utils and dependencies
RUN yum install -y tar \
    && yum clean all && \
      yum -y install openssl \
      lsof lshw net-tools numactl \
      sysstat wget screen psmisc \
      zip unzip glibc glibc-devel \
      openssh-server libssl0.9.8 \
      tcpdump iptables psmisc  initscripts

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


RUN mkdir /var/run/sshd
RUN echo 'root:couchbase' | chpasswd
RUN sed -i 's/PermitRootLogin without-password/PermitRootLogin yes/' /etc/ssh/sshd_config

# SSH login fix. Otherwise user is kicked off after login
RUN sed 's@session\s*required\s*pam_loginuid.so@session optional pam_loginuid.so@g' -i /etc/pam.d/sshd

RUN echo "export VISIBLE=now" >> /etc/profile


# Create Couchbase user with UID 1000 (necessary to match default
# boot2docker UID)
RUN groupadd -g1000 couchbase && \
    useradd couchbase -g couchbase -u1000 -m -s /bin/bash && \
    echo 'couchbase:couchbase' | chpasswd


ARG VERSION=5.0.0
ARG BUILD_NO=2412
ARG FLAVOR=spock
ARG BUILD_PKG=couchbase-server-enterprise-$VERSION-$BUILD_NO-centos7.x86_64.rpm
ARG BASE_URL=http://172.23.120.24/builds/latestbuilds/couchbase-server/$FLAVOR/$BUILD_NO

ARG BUILD_URL=$BASE_URL/$BUILD_PKG
RUN echo $BUILD_URL && \
    wget -N $BUILD_URL

# Install couchbase
RUN yum install -y $BUILD_PKG

#clean the cache
RUN yum clean all


# custom startup scripts
COPY scripts/couchbase-start /usr/local/bin/
RUN mv /bin/systemctl /bin/systemctl.bin
COPY scripts/systemctl /bin/systemctl


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
COPY start.sh /start.sh

EXPOSE 8091 8092 8093 8094 9100 9101 9102 9103 9104 9105 9998 9999 11207 11210 11211 18091 18092 22
ARG MEMBASE_RAM_MEGS=0
RUN bash -c '[[ $MEMBASE_RAM_MEGS != 0 ]] && sed  -i "s/export PATH/export PATH\nMEMBASE_RAM_MEGS=$MEMBASE_RAM_MEGS\nexport MEMBASE_RAM_MEGS/" /opt/couchbase/bin/couchbase-server || true'

RUN echo "*        soft    nproc           unlimited" >> /etc/security/limits.conf
RUN echo "*        hard    nproc           unlimited" >> /etc/security/limits.conf
RUN echo "ulimit -u unlimited" >> /home/couchbase/.bashrc
RUN sed -i 's/--user couchbase/--user root/' /etc/init.d/couchbase-server || true

CMD ["./start.sh"]
# pass -noinput so it doesn't drop us in the erlang shell

#VOLUME /opt/couchbase/var

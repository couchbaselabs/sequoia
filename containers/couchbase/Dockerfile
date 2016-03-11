FROM ubuntu:14.04
RUN apt-get update

RUN apt-get install -yq runit wget python-httplib2  openssh-server  && \
    apt-get autoremove && apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

ENV NOTVISIBLE="in users profile" \
    PATH=$PATH:/opt/couchbase/bin:/opt/couchbase/bin/tools:/opt/couchbase/bin/install \
    LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/opt/couchbase/lib \
    BUILD_NO=1307 \
    BASE_URL=http://172.23.120.24/builds/latestbuilds/couchbase-server/watson
ENV BUILD_PKG=couchbase-server-enterprise_4.5.0-$BUILD_NO-ubuntu14.04_amd64.deb

RUN mkdir /var/run/sshd
RUN echo 'root:couchbase' | chpasswd
RUN sed -i 's/PermitRootLogin without-password/PermitRootLogin yes/' /etc/ssh/sshd_config

# SSH login fix. Otherwise user is kicked off after login
RUN sed 's@session\s*required\s*pam_loginuid.so@session optional pam_loginuid.so@g' -i /etc/pam.d/sshd

RUN echo "export VISIBLE=now" >> /etc/profile


# Create Couchbase user with UID 1000 (necessary to match default
# boot2docker UID)
RUN groupadd -g 1000 couchbase && useradd couchbase -u 1000 -g couchbase -M

# Install couchbase
ENV BUILD_URL=$BASE_URL/$BUILD_NO/$BUILD_PKG
RUN echo $BUILD_URL && \
    wget -N $BUILD_URL && \
    dpkg -i ./$BUILD_PKG && rm -f ./$BUILD_PKG

# Add runit script for couchbase-server
COPY scripts/run /etc/service/couchbase-server/run

# Add bootstrap script
COPY scripts/entrypoint.sh /

EXPOSE 8091 8092 8093 11207 11210 11211 18091 18092 22
VOLUME /opt/couchbase/var

COPY start.sh /start.sh
CMD "./start.sh"


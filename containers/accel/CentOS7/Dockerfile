FROM centos/systemd

ARG VERSION=1.4.1
ARG BUILD_NO=3

ENV PATH $PATH:/opt/couchbase-sg-accel/bin
ENV PKG couchbase-sg-accel-enterprise_${VERSION}-${BUILD_NO}_x86_64.rpm

# Install dependencies:
#  wget: for downloading Sync Gateway package installer
RUN yum -y update && \
    yum install -y \
    wget perl && \
    yum clean all

# Install Sync Gateway
RUN wget http://latestbuilds.service.couchbase.com/builds/latestbuilds/sync_gateway/$VERSION/$BUILD_NO/$PKG && \
    rpm -i $PKG && \
    rm $PKG

# Add the default config into the container
ADD config/config.json /home/sg_accel/sg_accel.json

ADD entrypoint.sh /entrypoint.sh

# Expose ports
#  port 4984: public port
EXPOSE 4984

# Invoke the sync_gateway executable by default
CMD ["/usr/sbin/init"]

FROM centos:7

# NOTE building this container requires access to sdk repo
# the following folders should be cloned before doing a build here
#  * git@github.com:couchbaselabs/sdkdclient-ng.git
#  * git@github.com:couchbase/sdkd-java.git

# enviornment
RUN yum update -y; yum install -y which java-1.8.0-openjdk-devel git wget
RUN yum install -y openssl-devel

WORKDIR /root

# install maven 3.3.9
RUN wget http://www-eu.apache.org/dist/maven/maven-3/3.3.9/binaries/apache-maven-3.3.9-bin.tar.gz
RUN tar xzf apache-maven-3.3.9-bin.tar.gz
RUN ln -s apache-maven-3.3.9 maven
ENV PATH=${PATH}:/root/maven/bin

# checkout java sdk
RUN git clone git://github.com/couchbase/couchbase-jvm-core.git
RUN (cd couchbase-jvm-core && git checkout 1.4.5 && git log -n 2)
RUN git clone git://github.com/couchbase/couchbase-java-client.git
RUN (cd couchbase-java-client && git checkout 2.4.5 && git log -n 2)

# build sdkd
ADD sdkd-java /root/sdkd-java
RUN ls -al /root/sdkd-java/
RUN cp sdkd-java/util/buildSDKDJar.sh .
RUN ./buildSDKDJar.sh

# install sdkdclient
ADD sdkdclient-ng /root/sdkdclient-ng
WORKDIR /root/sdkdclient-ng
RUN mvn package -Dmaven.test.skip=true
ENV BRUN_PERCENTILE=85
#RUN mapfile -c 1 -C subst
RUN mkdir -p pylib
#RUN cp /root/sdkd-cpp/pylib/s3upload.py pylib/s3upload.py
ADD S3Creds_tmp S3Creds_tmp
COPY brun brun
COPY host2ip.sh host2ip.sh

# add runtime ini-files
COPY spock-basic.ini spock-basic.ini
RUN sed -i 's/num_containers.*//' spock-basic.ini
ENTRYPOINT ["./brun"]

FROM centos:7

# NOTE building this container requires access to sdk repo
# the following folders should be cloned before doing a build here
#  * git@github.com:couchbaselabs/sdkdclient-ng.git
#  * git@github.com:couchbase/sdkd-cpp.git

ARG SDK=java
ARG SDK_COMMIT=master
ARG CORE_COMMIT=master

WORKDIR /root
# install base packages
RUN yum update -y
RUN yum install -y java-1.8.0-openjdk-devel git wget openssl-devel
ENV JAVA_HOME=/usr/lib/jvm/java


# install maven 3.3.9
RUN wget http://www-eu.apache.org/dist/maven/maven-3/3.3.9/binaries/apache-maven-3.3.9-bin.tar.gz
RUN tar xzf apache-maven-3.3.9-bin.tar.gz
RUN ln -s apache-maven-3.3.9 maven
ENV PATH=${PATH}:/root/maven/bin


# enviornment to build sdk
ADD $SDK /root/$SDK
WORKDIR /root/$SDK
RUN ./environment.sh

# build sdkd with sdk
RUN ./build.sh $SDK_COMMIT $CORE_COMMIT

# install sdkdclient
ADD sdkdclient-ng /root/sdkdclient-ng
WORKDIR /root/sdkdclient-ng
RUN mvn package -q -Dmaven.test.skip=true
ENV BRUN_PERCENTILE=85
ADD S3Creds_tmp S3Creds_tmp
ADD brun brun
ADD host2ip.sh host2ip.sh

# add runtime ini-files
ADD spock-basic.ini spock-basic.ini
RUN sed -i 's/num_containers.*//' spock-basic.ini

ENTRYPOINT ["./brun"]

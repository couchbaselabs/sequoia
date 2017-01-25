from centos:7

# enviornment
RUN yum update -y; yum install -y java-1.8.0-openjdk-devel maven git
COPY logback.xml /tmp/
ENV PACKAGE_NAME=java-dcp-client \
    MAVEN_OPTS="-Dlogback.configurationFile=/tmp/logback.xml  -DLOG_DIR=/log"


# pull sdk test repo 
WORKDIR / 
RUN git clone https://github.com/couchbaselabs/java-dcp-client 
WORKDIR /java-dcp-client


# build  client
ARG COMMIT=master
RUN git checkout $COMMIT
RUN mvn clean install -DskipTests=true -Dmaven.repo.local=/tmp

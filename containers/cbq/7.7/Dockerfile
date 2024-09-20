FROM ubuntu:20.04
WORKDIR /
RUN apt-get update
RUN apt-get install -y git wget
RUN wget http://172.23.126.166/builds/latestbuilds/couchbase-server/cypher/1208/couchbase-server-dev-tools-7.7.0-1208-linux_x86_64.tar.gz
RUN tar -xf couchbase-server-dev-tools-7.7.0-1208-linux_x86_64.tar.gz
WORKDIR couchbase-server-dev-tools-7.7.0-1208/bin
ENTRYPOINT ["./cbq"]
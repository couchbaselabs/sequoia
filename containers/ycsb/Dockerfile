FROM ubuntu:14.04

WORKDIR /root

RUN apt-get update && \
    apt-get install -y git python-dev python-pip curl libc6 libcurl3 zlib1g
CMD apt-get install mvn
CMD git clone https://github.com/daschl/YCSB.git

WORKDIR  /root/YCSB

CMD git fetch origin
CMD git checkout origin/refresh
CMD mvn -pl com.yahoo.ycsb:couchbase2-binding -am clean package -Dmaven.test.skip -Dcheckstyle.skip=true

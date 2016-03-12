FROM ubuntu_python

WORKDIR /root
RUN apt-get install -y curl libc6 libcurl3 zlib1g
RUN yes | apt-get install maven
RUN yes | apt-get install default-jdk
RUN git clone https://github.com/daschl/YCSB
RUN ls -l
WORKDIR  /root/YCSB
RUN git fetch origin
RUN git checkout origin/refresh
RUN mvn -pl com.yahoo.ycsb:couchbase2-binding -am clean package -Dmaven.test.skip -Dcheckstyle.skip=true
COPY run.sh run.sh
COPY create_index.sql create_index.sql


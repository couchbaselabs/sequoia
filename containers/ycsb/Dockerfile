FROM ubuntu_python

WORKDIR /root
RUN apt-get install -y curl libc6 libcurl3 zlib1g mvn
CMD git clone https://github.com/daschl/YCSB.git

WORKDIR  /root/YCSB

CMD git fetch origin
CMD git checkout origin/refresh
CMD mvn -pl com.yahoo.ycsb:couchbase2-binding -am clean package -Dmaven.test.skip -Dcheckstyle.skip=true

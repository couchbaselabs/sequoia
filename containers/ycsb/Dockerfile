WORKDIR /root

CMD apt-get install mvn
CMD rm -rf YCSB
CMD git clone https://github.com/daschl/YCSB.git
CMD cd YCSB
CMD git fetch origin
CMD git checkout origin/refresh
CMD mvn -pl com.yahoo.ycsb:couchbase2-binding -am clean package -Dmaven.test.skip -Dcheckstyle.skip=true
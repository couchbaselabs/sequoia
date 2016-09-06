FROM ubuntu_vbr
#RUN killall java
RUN ls -la
#RUN /bin/bash -c "cd /CbTest ; ./startLoader.sh"
#RUN cd CbTest && java -Xmx1g -Xms256m -cp testCB.jar:lib/gson-2.2.1.jar:lib/log4j-1.2.17.jar:lib/ini4j-0.5.2.jar:lib/jedis-2.1.0.jar:lib/commons-codec-1.5.jar:lib/couchbase-client-1.1.0.jar:lib/jettison-1.1.jar:lib/netty-3.5.5.Final.jar:lib/spymemcached-2.8.9.jar:lib/httpcore-4.1.1.jar:lib/httpcore-nio-4.1.1.jar com.viber.largescaletest.DbJobProcessor &
#WORKDIR /root/redis-stable/src/
#RUN /bin/bash -c "./redis-server &"
#run sleep 5
WORKDIR /root/CbTest/
ENTRYPOINT ["./startLoader.sh"]
#ENTRYPOINT ["java -Xmx1g -Xms256m -cp testCB.jar:lib/gson-2.2.1.jar:lib/log4j-1.2.17.jar:lib/ini4j-0.5.2.jar:lib/jedis-2.1.0.jar:lib/commons-codec-1.5.jar:lib/couchbase-client-1.1.0.jar:lib/jettison-1.1.jar:lib/netty-3.5.5.Final.jar:lib/spymemcached-2.8.9.jar:lib/httpcore-4.1.1.jar:lib/httpcore-nio-4.1.1.jar com.viber.largescaletest.DbJobProcessor &"]




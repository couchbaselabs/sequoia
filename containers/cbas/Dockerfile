FROM ubuntu_cbas
RUN ls -la
WORKDIR /root/cbas/cbas
RUN sed -i '$ d' ./samples/local/bin/start-sample-cluster.sh
RUN echo "ifconfig" >> ./samples/local/bin/start-sample-cluster.sh
RUN echo "sleep 100000" >> ./samples/local/bin/start-sample-cluster.sh
ENV JAVA_HOME /usr/lib/jvm/java-8-oracle
ENTRYPOINT ["./samples/local/bin/start-sample-cluster.sh"]
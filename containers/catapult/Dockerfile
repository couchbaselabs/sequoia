# install java
FROM adoptopenjdk/openjdk12:latest
WORKDIR /root

# install base packages
RUN apt-get update
RUN apt-get install -y git wget

# install maven 3.6.3
RUN wget https://downloads.apache.org/maven/maven-3/3.6.3/binaries/apache-maven-3.6.3-bin.tar.gz
RUN tar xzf apache-maven-3.6.3-bin.tar.gz
RUN ln -s apache-maven-3.6.3 maven
ENV PATH=${PATH}:/root/maven/bin

# src
RUN git clone https://github.com/couchbaselabs/java_sdk_client.git
WORKDIR java_sdk_client/collections
RUN git pull
RUN mvn package -q -Dmaven.test.skip=true
WORKDIR target/javaclient
COPY run.sh run.sh
ENTRYPOINT ["./run.sh"]
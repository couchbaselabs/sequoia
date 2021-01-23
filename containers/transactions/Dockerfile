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
RUN git clone https://github.com/couchbaselabs/productivitynautomation
WORKDIR productivitynautomation/transaction-performer
RUN git pull
RUN mvn clean package
WORKDIR target/
COPY run.sh run.sh
ENTRYPOINT ["./run.sh"]

FROM adoptopenjdk/openjdk12:latest
WORKDIR /root

# install base packages
RUN apt-get update
RUN apt-get install -y git wget

# install maven 3.6.3
RUN wget https://downloads.apache.org/maven/maven-3/3.9.6/binaries/apache-maven-3.9.6-bin.tar.gz
RUN tar xzf apache-maven-3.9.6-bin.tar.gz
RUN ln -s apache-maven-3.9.6 maven
ENV PATH=${PATH}:/root/maven/bin

# src
RUN git clone https://github.com/couchbaselabs/DocLoader.git
WORKDIR DocLoader
RUN mvn -f pom.xml clean install
WORKDIR target/magmadocloader
ENV TZ=US/Pacific
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
RUN apt-get install -y git git-all python3-dev python3-pip python3-setuptools cmake build-essential libssl-dev
RUN python3 -m  pip install requests six future couchbase==3.0.10 httplib2 dnspython
COPY magmaloader.py magmaloader.py
ENTRYPOINT ["python3","-u", "magmaloader.py"]

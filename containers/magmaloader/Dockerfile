FROM --platform=linux/amd64 adoptopenjdk/openjdk12:latest
ARG CACHEBUST=1
WORKDIR /root
# Force cache invalidation and set environment
RUN echo "Cache bust: $CACHEBUST" && \
    echo "Target platform: $TARGETPLATFORM" && \
    export TZ=US/Pacific && \
    echo "Timezone set to: $TZ"
ARG TARGETPLATFORM
ENV TZ=US/Pacific
# install base packages
RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -yq --no-install-recommends
RUN apt-get install -y git wget

# install maven 3.6.3
RUN wget https://archive.apache.org/dist/maven/maven-3/3.9.11/binaries/apache-maven-3.9.11-bin.tar.gz
RUN tar xzf apache-maven-3.9.11-bin.tar.gz
RUN ln -s apache-maven-3.9.11 maven
ENV PATH=${PATH}:/root/maven/bin

# src
RUN git clone https://github.com/couchbaselabs/DocLoader.git
WORKDIR DocLoader
RUN git pull
RUN echo git log
RUN mvn -f pom.xml clean install
WORKDIR target/magmadocloader
ENV TZ=US/Pacific
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
# magmaloader.py only imports requests and dns.resolver (dnspython); the loading is done by the Java loader built above.
# No git-all / build toolchain / couchbase SDK: those pulled ~400 packages (1 GB) and built the SDK from source for nothing.
RUN apt-get install -y --no-install-recommends python3-pip python3-setuptools python3-wheel && rm -rf /var/lib/apt/lists/*
RUN python3 -m pip install --no-cache-dir requests dnspython
COPY magmaloader.py magmaloader.py
ENTRYPOINT ["python3","-u", "magmaloader.py"]

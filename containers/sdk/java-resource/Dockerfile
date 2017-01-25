FROM sequoiatools/sdk-java-client

RUN mkdir /log; mkdir /status 

# pull sdk test repo 
WORKDIR /
RUN git clone --recursive https://github.com/tahmmee/sdk-data

# build all client resources (currently only 'basic')
ENV PACKAGE_NAME=basic
WORKDIR /sdk-data/client/$PACKAGE_NAME
RUN mvn clean package -DskipTests=true -Dmaven.repo.local=/tmp

# build all workload resources (currently only 'dcp')
ENV WORKLOAD=dcp/generator
WORKDIR /sdk-data/workload/$WORKLOAD
RUN mvn clean package -DskipTests=true -Dmaven.repo.local=/tmp

WORKDIR /
COPY client.sh /client
COPY workload.sh /workload

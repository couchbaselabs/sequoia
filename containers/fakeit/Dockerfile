FROM centos:7
MAINTAINER vikas chaudhary <vikas.chaudhary@couchbase.com>

RUN rm /bin/sh && ln -s /bin/bash /bin/sh

RUN yum update -y
RUN yum install -y git wget openssl-devel

# c and python sdk
RUN wget http://packages.couchbase.com/releases/couchbase-release/couchbase-release-1.0-6-x86_64.rpm
RUN rpm -iv couchbase-release-1.0-6-x86_64.rpm
RUN yum -y install libcouchbase-devel libcouchbase2-bin gcc gcc-c++
RUN yum -y install gcc gcc-c++ python-devel epel-release epel-devel
RUN yum -y install python-pip
RUN yum -y install make
RUN pip install --upgrade setuptools
RUN pip install couchbase

ENV NVM_VERSION 0.33.8
ENV NODE_VERSION 9.11.2
ENV NVM_DIR /.nvm
RUN curl https://raw.githubusercontent.com/creationix/nvm/v0.33.8/install.sh | bash 

RUN source ~/.bashrc \
    && nvm install 9 \
    && nvm alias default 9 \
    && nvm use default
ENV NODE_PATH $NVM_DIR/v$NODE_VERSION/lib/node_modules
ENV PATH $NVM_DIR/versions/node/v$NODE_VERSION/bin:$PATH

RUN node -v
RUN npm -v

# install fake it 
RUN git clone https://github.com/bentonam/fakeit.git
RUN cd fakeit && make install && make build && npm link

WORKDIR /fakeit
COPY links_big.yaml /fakeit/test/fixtures/models/links/models/
RUN chmod 777 /fakeit/test/fixtures/models/links/models/links_big.yaml
ENTRYPOINT ["fakeit"]

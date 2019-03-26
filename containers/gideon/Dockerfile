FROM sequoiatools/pillowfight

RUN apt-get update
RUN apt-get install -y python-dev python-pip

# python deps
RUN pip install gevent==1.2.1

WORKDIR /root

WORKDIR /root
RUN pip install pyyaml && \
    pip install eventlet && \
    pip install requests

RUN pip install git+git://github.com/couchbase/couchbase-python-client

# src
RUN git clone https://github.com/couchbaselabs/gideon.git
RUN apt-get install curl
WORKDIR gideon
RUN git pull

COPY spec.yaml /spec.yaml
COPY views.json views.json
COPY addviews.sh addviews.sh 
COPY run.sh run.sh
ENTRYPOINT ["./run.sh"]

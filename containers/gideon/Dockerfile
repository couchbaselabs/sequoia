FROM pillowfight

RUN apt-get install -y python-dev python-pip

# python deps
RUN pip install gevent

WORKDIR /root

WORKDIR /root
RUN pip install git+git://github.com/couchbase/couchbase-python-client &&\
    pip install pyyaml && \
    pip install eventlet

# src
RUN git clone https://github.com/couchbaselabs/gideon.git
WORKDIR gideon

COPY spec.yaml /spec.yaml
ENTRYPOINT ["python", "gideon.py"]

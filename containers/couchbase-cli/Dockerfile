FROM tleyden5iwx/centos-6-python-2.7 
RUN yum install -y git
RUN git clone https://github.com/couchbase/couchbase-cli.git
ENV CB_REST_USERNAME=Administrator \
     CB_REST_PASSWORD=password
WORKDIR couchbase-cli
ENTRYPOINT ["./couchbase-cli"]

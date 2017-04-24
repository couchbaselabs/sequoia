FROM python:2.7
RUN git clone https://github.com/couchbase/couchbase-cli.git
ENV CB_REST_USERNAME=Administrator \
     CB_REST_PASSWORD=password
WORKDIR couchbase-cli
RUN git config --global user.email "staff_qe@couchbase.com"
RUN git config --global user.name "Staff QE"
ENTRYPOINT ["./couchbase-cli"]

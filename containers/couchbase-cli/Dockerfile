FROM python:3
RUN git clone https://github.com/couchbase/couchbase-cli.git
ENV CB_REST_USERNAME=Administrator \
     CB_REST_PASSWORD=password
WORKDIR couchbase-cli
RUN echo "VERSION=\"8.5.0-1009-enterprise\"" > cb_version.py
ADD couchbase-cli-secure /couchbase-cli-secure
ENTRYPOINT ["./couchbase-cli"]

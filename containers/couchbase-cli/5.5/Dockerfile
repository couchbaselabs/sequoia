FROM python:2.7
RUN git clone https://github.com/couchbase/couchbase-cli.git
ENV CB_REST_USERNAME=Administrator \
     CB_REST_PASSWORD=password
WORKDIR couchbase-cli
RUN git checkout vulcan
RUN echo "VERSION=\"5.5.4-4340-enterprise\"" > cb_version.py
ADD couchbase-cli-secure /couchbase-cli-secure
ENTRYPOINT ["./couchbase-cli"]

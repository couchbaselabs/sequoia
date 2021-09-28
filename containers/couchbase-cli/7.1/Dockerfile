FROM python:3.7
RUN python3 -m  pip install requests
RUN git clone https://github.com/couchbase/couchbase-cli.git
ENV CB_REST_USERNAME=Administrator \
     CB_REST_PASSWORD=password
WORKDIR couchbase-cli
RUN git checkout master
RUN echo "VERSION=\"7.1.0-1345-enterprise\"" > cb_version.py
ADD couchbase-cli-secure /couchbase-cli-secure
ENTRYPOINT ["./couchbase-cli"]

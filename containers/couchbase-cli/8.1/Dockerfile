FROM python:3.7-slim

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir \
    requests \
    pycryptodome \
    pem \
    cryptography \
    pyOpenSSL

RUN git clone https://github.com/couchbase/couchbase-cli.git

ENV CB_REST_USERNAME=Administrator \
     CB_REST_PASSWORD=password
WORKDIR couchbase-cli
RUN git checkout master
RUN echo "VERSION=\"8.1.0-2127-enterprise\"" > cb_version.py
ADD couchbase-cli-secure /couchbase-cli-secure
ENTRYPOINT ["./couchbase-cli"]

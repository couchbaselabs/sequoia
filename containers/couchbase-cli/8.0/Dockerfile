FROM python:3.7
RUN python3 -m  pip install requests
RUN python3 -m  pip install pycryptodome
RUN python3 -m  pip install pem
RUN python3 -m  pip install cryptography
RUN python3 -m  pip install pyOpenSSL
RUN git clone https://github.com/couchbase/couchbase-cli.git
ENV CB_REST_USERNAME=Administrator \
     CB_REST_PASSWORD=password
WORKDIR couchbase-cli
RUN git checkout master
RUN echo "VERSION=\"8.0.0-1600-enterprise\"" > cb_version.py
ADD couchbase-cli-secure /couchbase-cli-secure
ENTRYPOINT ["./couchbase-cli"]

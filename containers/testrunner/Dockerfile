FROM ubuntu_python
RUN git clone git://github.com/couchbase/testrunner.git
WORKDIR testrunner

RUN pip install gevent &&\
    pip install paramiko &&\
    pip install boto
COPY local.ini local.ini
COPY upgrade_local.ini upgrade_local.ini
COPY host2ip.sh host2ip.sh
COPY testrunner testrunner
ENTRYPOINT ["./testrunner"]

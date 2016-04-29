FROM ubuntu_python
RUN git clone git://github.com/couchbase/testrunner.git
WORKDIR testrunner

RUN pip install gevent &&\
    pip install boto
RUN apt-get install -y libssl-dev libffi-dev
RUN easy_install paramiko

COPY local.ini local.ini
COPY upgrade_local.ini upgrade_local.ini
COPY host2ip.sh host2ip.sh
COPY testrunner testrunner
ENTRYPOINT ["./testrunner"]

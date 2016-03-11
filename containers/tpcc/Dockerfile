FROM ubuntu:14.04

WORKDIR /root
RUN apt-get update && \
    apt-get install -y git python-dev python-pip curl libc6 libcurl3 zlib1g
RUN git clone https://github.com/couchbaselabs/py-tpcc.git
WORKDIR /root/py-tpcc/pytpcc
COPY run.sh run.sh
RUN chmod 777 ./run.sh
RUN chmod 777 ./util/run_sql.sh

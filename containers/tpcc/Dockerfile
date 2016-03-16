FROM ubuntu_python

WORKDIR /root
RUN apt-get install -y curl libc6 libcurl3 zlib1g
RUN git clone https://github.com/couchbaselabs/py-tpcc.git
WORKDIR /root/py-tpcc/pytpcc
COPY run.sh run.sh
COPY change_engine.sh change_engine.sh
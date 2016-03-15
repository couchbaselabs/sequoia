FROM ubuntu_gcc

RUN apt-get install -y python-dev python-pip wget cmake

# Install libcouchbase
RUN git clone git://github.com/couchbase/libcouchbase.git && \
    mkdir libcouchbase/build

WORKDIR libcouchbase/build
RUN ../cmake/configure --prefix=/usr && \
      make && \
      make install

WORKDIR /root
RUN pip install spring
WORKDIR spring

FROM ubuntu_gcc

WORKDIR /root


RUN git clone git://github.com/couchbase/libcouchbase.git && \
    mkdir libcouchbase/build

WORKDIR libcouchbase/build
RUN ../cmake/configure --prefix=/usr && \
      make && \
      make install

WORKDIR bin
ENTRYPOINT ["cbc-pillowfight"]

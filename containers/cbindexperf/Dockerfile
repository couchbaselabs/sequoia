FROM google/golang
ENV GOPATH=$HOME/query/
RUN mkdir -p $GOPATH/src/github.com/couchbase/
WORKDIR ~/query
RUN mkdir bin pkg
WORKDIR $GOPATH/src/github.com/couchbase/
RUN git clone https://github.com/couchbase/query query
WORKDIR query/
RUN ./build.sh 
WORKDIR ../indexing/secondary/cmd/cbindexperf/
RUN  go build 
COPY config.json /root/config.json
ENTRYPOINT ["./cbindexperf","-configfile","/root/config.json"]

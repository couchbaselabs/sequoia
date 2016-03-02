docker rm  $(docker ps -aq)
docker pull martin/wait
docker build -t gideon containers/gideon/
docker build -t perfrunner containers/perfrunner/
docker build -t couchbase-watson couchbase/
docker build -t couchbase-cli containers/couchbase-cli
docker build -t testrunner containers/testrunner
docker build -t tpcc containers/tpcc
docker build -t ycsb containers/ycsb
npm install

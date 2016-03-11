# public images
docker pull martin/wait

# base template
docker build -t ubuntu_gcc -f containers/templates/Dockerfile-ubuntu-gcc  containers/templates/
docker build -t ubuntu_python -f containers/templates/Dockerfile-ubuntu-python  containers/templates/

# framework containers
docker build -t perfrunner containers/perfrunner
docker build -t couchbase-watson containers/couchbase
docker build -t couchbase-cli containers/couchbase-cli
docker build -t testrunner containers/testrunner
docker build -t tpcc containers/tpcc
docker build -t ycsb containers/ycsb
docker build -t pillowfight containers/pillowfight
docker build -t gideon containers/gideon  # depends on pillowfight

# build framework
npm install

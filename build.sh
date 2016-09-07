BUILD_NO=${1:-1818}

# public images
docker pull martin/wait
docker pull clue/httpie

# base template
docker build -t ubuntu_gcc -f containers/templates/Dockerfile-ubuntu-gcc  containers/templates/
docker build -t ubuntu_python -f containers/templates/Dockerfile-ubuntu-python  containers/templates/
docker build -t ubuntu_vbr -f containers/templates/Dockerfile-ubuntu-vbr  containers/templates/

# framework containers
docker build -t sequoiatools/perfrunner containers/perfrunner
docker build --build-arg BUILD_NO=$BUILD_NO -t couchbase-watson containers/couchbase
docker build -t sequoiatools/couchbase-cli containers/couchbase-cli
docker build -t sequoiatools/testrunner containers/testrunner
docker build -t sequoiatools/tpcc containers/tpcc
docker build -t sequoiatools/pillowfight containers/pillowfight
docker build -t sequoiatools/gideon containers/gideon  # depends on pillowfight
docker build -t sequoiatools/vbr containers/vbr
#docker build -t ycsb containers/ycsb
#docker build -t mysql containers/mysql
#docker build -t elasticsearch containers/elasticsearch
#docker build -t mortimer containers/mortimer
#docker build -t jinja containers/jinja
#docker build -t cbq containers/cbq

# build framework
npm install

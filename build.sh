docker rm  $(docker ps -aq)
docker pull martin/wait
docker build -t ansible  ansible/
docker build -t gideon frameworks/gideon/
docker build -t perfrunner-n1ql frameworks/perfrunner/
docker build -t couchbase-watson couchbase/
docker build -t couchbase-cli frameworks/couchbase-cli
npm install

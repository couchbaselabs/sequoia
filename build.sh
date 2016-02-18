docker rm $(docker ps -q -f status=exited)
docker build -t ansible  ansible/
docker build -t gideon frameworks/gideon/
docker build -t perfrunner-n1ql frameworks/perfrunner/
docker build -t couchbase-4.1 couchbase/
docker build -t couchbase-cli frameworks/couchbase-cli

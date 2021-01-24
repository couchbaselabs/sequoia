#!/bin/bash

for ARGUMENT in "$@"
do

    KEY=$(echo $ARGUMENT | cut -f1 -d=)
    VALUE=$(echo $ARGUMENT | cut -f2 -d=)   

    case "$KEY" in
            MOBILE_TESTKIT_BRANCH)          MOBILE_TESTKIT_BRANCH=${VALUE} ;;
            COUCHBASE_SERVER_VERSION)       COUCHBASE_SERVER_VERSION=${VALUE} ;;
            SYNC_GATEWAY_VERSION)           SYNC_GATEWAY_VERSION=${VALUE} ;;     
            CBLITE_VERSIONS)                CBLITE_VERSIONS=${VALUE} ;;
            CBLITE_HOSTS)                   CBLITE_HOSTS=${VALUE} ;;
            CBLITE_PLATFORM)                CBLITE_PLATFORM=${VALUE} ;;
            NUM_OF_DOCS)                    NUM_OF_DOCS=${VALUE} ;;
            NUM_OF_DOC_UPDATES)             NUM_OF_DOC_UPDATES=${VALUE} ;;
            NUM_OF_DOCS_TO_UPDATE)          NUM_OF_DOCS_TO_UPDATE=${VALUE} ;;
            NUM_OF_DOCS_TO_DELETE)          NUM_OF_DOCS_TO_DELETE=${VALUE} ;;
            NUM_OF_DOCS_IN_ITR)             NUM_OF_DOCS_IN_ITR=${VALUE} ;;
            NUM_OF_DOCS_TO_ADD)             NUM_OF_DOCS_TO_ADD=${VALUE} ;;
            REPL_STATUS_CHECK_SLEEP_TIME)   REPL_STATUS_CHECK_SLEEP_TIME=${VALUE} ;;
            UP_TIME)                        UP_TIME=${VALUE} ;;
            LITESERV_USER)                  LITESERV_USER=${VALUE} ;;
            LITESERV_PWD)                   LITESERV_PWD=${VALUE} ;;
            SSH_USER)                       SSH_USER=${VALUE} ;;
            SSH_PWD)                        SSH_PWD=${VALUE} ;;
            USE_LOCAL_TESTSERVER)           USE_LOCAL_TESTSERVER=${VALUE} ;;
            CBS_HOSTS)                      CBS_HOSTS=${VALUE} ;;
            SGW_HOSTS)                      SGW_HOSTS=${VALUE} ;;
            MODE)                           MODE=${VALUE} ;;
            TEST_NAME)                      TEST_NAME=${VALUE} ;;
            *)   
    esac    

done

echo "MOBILE_TESTKIT_BRANCH = $MOBILE_TESTKIT_BRANCH"
echo "COUCHBASE_SERVER_VERSION = $COUCHBASE_SERVER_VERSION"
echo "SYNC_GATEWAY_VERSION = $SYNC_GATEWAY_VERSION"
echo "CBLITE_VERSIONS = $CBLITE_VERSIONS"
echo "CBLITE_HOSTS = $CBLITE_HOSTS"
echo "CBLITE_PLATFORM=$CBLITE_PLATFORM"
echo "NUM_OF_DOCS = $NUM_OF_DOCS"
echo "NUM_OF_DOC_UPDATES = $NUM_OF_DOC_UPDATES"
echo "NUM_OF_DOCS_TO_UPDATE = $NUM_OF_DOCS_TO_UPDATE"
echo "NUM_OF_DOCS_TO_DELETE = $NUM_OF_DOCS_TO_DELETE"
echo "NUM_OF_DOCS_IN_ITR = $NUM_OF_DOCS_IN_ITR"
echo "NUM_OF_DOCS_TO_ADD = $NUM_OF_DOCS_TO_ADD"
echo "REPL_STATUS_CHECK_SLEEP_TIME = $REPL_STATUS_CHECK_SLEEP_TIME"
echo "UP_TIME = $UP_TIME"
echo "LITESERV_USER = $LITESERV_USER"
echo "LITESERV_PWD = $LITESERV_PWD"
echo "SSH_USER = $SSH_USER"
echo "SSH_PWD = $SSH_PWD"
echo "USE_LOCAL_TESTSERVER = $USE_LOCAL_TESTSERVER"
echo "CBS_HOSTS = $CBS_HOSTS"
echo "SGW_HOSTS = $SGW_HOSTS"
echo "MODE = $MODE"
echo "TEST_NAME = $TEST_NAME"

git checkout $MOBILE_TESTKIT_BRANCH
git pull origin $MOBILE_TESTKIT_BRANCH
git fetch
git reset --hard origin/$MOBILE_TESTKIT_BRANCH

export LITESERV_MSFT_HOST_USER=${LITESERV_USER}
export LITESERV_MSFT_HOST_PASSWORD=${LITESERV_PWD}
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

source setup.sh

# Print commands / output
set -x

# Exit if a command exits with a non-zero status
set -e

# create pool.json and ansible.cfg
python utilities/sequoia_env_prep.py --ssh-user=${SSH_USER} --cbs-hosts=${CBS_HOSTS} --sgw-hosts=${SGW_HOSTS}
cat ./resources/pool.json
cat ansible.cfg

python libraries/utilities/generate_clusters_from_pool.py
python libraries/utilities/install_keys.py --public-key-path=~/.ssh/id_rsa.pub --ssh-user=${SSH_USER} --ssh-password=${SSH_PWD}

if [ -z "$TEST_NAME" ] 
then
	TEST_KEYWORD=""
else
	TEST_KEYWORD="-k $TEST_NAME"
fi


echo "Running system test"
pytest -s -rsx \
  --timeout 864000 ${TEST_KEYWORD} \
  --liteserv-versions=${CBLITE_VERSIONS} \
  --liteserv-hosts=${CBLITE_HOSTS} \
  --liteserv-ports=8080 \
  --liteserv-platforms=${CBLITE_PLATFORM} \
  --xattrs --enable-file-logging --delta-sync --no-db-delete \
  --skip-provisioning \
  --sequoia \
  --num-of-docs=${NUM_OF_DOCS} \
  --num-of-doc-updates=${NUM_OF_DOC_UPDATES} \
  --num-of-docs-to-update=${NUM_OF_DOCS_TO_UPDATE} \
  --num-of-docs-to-delete=${NUM_OF_DOCS_TO_DELETE} \
  --num-of-docs-in-itr=${NUM_OF_DOCS_IN_ITR} \
  --num-of-docs-to-add=${NUM_OF_DOCS_TO_ADD} \
  --up-time=${UP_TIME} \
  --repl-status-check-sleep-time=${REPL_STATUS_CHECK_SLEEP_TIME} \
  --sync-gateway-version=${SYNC_GATEWAY_VERSION} \
  --mode=${MODE} --server-version=${COUCHBASE_SERVER_VERSION} \
  --create-db-per-suite=cbl-test testsuites/CBLTester/System_test_multiple_device/test_system_testing.py
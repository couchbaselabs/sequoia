#!/bin/bash

for ARGUMENT in "$@"
do

    KEY=$(echo $ARGUMENT | cut -f1 -d=)
    VALUE=$(echo $ARGUMENT | cut -f2 -d=)   

    case "$KEY" in
            MOBILE_TESTKIT_BRANCH)          MOBILE_TESTKIT_BRANCH=${VALUE} ;;
            CBS_HOSTS)                      CBS_HOSTS=${VALUE} ;;
            COUCHBASE_SERVER_VERSION)       COUCHBASE_SERVER_VERSION=${VALUE} ;;
            SGW_HOSTS)                      SGW_HOSTS=${VALUE} ;;
            SYNC_GATEWAY_VERSION)           SYNC_GATEWAY_VERSION=${VALUE} ;;   
            COLLECT_LOGS)                   COLLECT_LOGS=${VALUE} ;;
            SERVER_SEED_DOCS)               SERVER_SEED_DOCS=${VALUE} ;;
            MAX_DOCS)                       MAX_DOCS=${VALUE} ;;
            NUM_USERS)                      NUM_USERS=${VALUE} ;;
            CREATE_BATCH_SIZE)              CREATE_BATCH_SIZE=${VALUE} ;;
            CREATE_DELAY)                   CREATE_DELAY=${VALUE} ;;
            UPDATE_BATCH_SIZE)              UPDATE_BATCH_SIZE=${VALUE} ;;
            UPDATE_DOCS_PERCENTAGE)         UPDATE_DOCS_PERCENTAGE=${VALUE} ;;
            UPDATE_DELAY)                   UPDATE_DELAY=${VALUE} ;;
            CHANGES_DELAY)                  CHANGES_DELAY=${VALUE} ;;
            CHANGES_LIMIT)                  CHANGES_LIMIT=${VALUE} ;;
            SSH_USER)                       SSH_USER=${VALUE} ;;
            SSH_PWD)                        SSH_PWD=${VALUE} ;;
            UP_TIME)                        UP_TIME=${VALUE} ;;
            *)
    esac

done

MOBILE_TESTKIT_BRANCH=${MOBILE_TESTKIT_BRANCH:-sequoia/sgw-component-testing}
COUCHBASE_SERVER_VERSION=${COUCHBASE_SERVER_VERSION:-7.0.0-4291}
SYNC_GATEWAY_VERSION=${SYNC_GATEWAY_VERSION:-2.8.0-374}
COLLECT_LOGS=${COLLECT_LOGS:-false} 
SERVER_SEED_DOCS=${SERVER_SEED_DOCS:-100000}
MAX_DOCS=${MAX_DOCS:-1200}
NUM_USERS=${NUM_USERS:-12}
CREATE_BATCH_SIZE=${CREATE_BATCH_SIZE:-1000}
CREATE_DELAY=${CREATE_DELAY:-0.1}
UPDATE_BATCH_SIZE=${UPDATE_BATCH_SIZE:-3}
UPDATE_DOCS_PERCENTAGE=${UPDATE_DOCS_PERCENTAGE:-0.1}
UPDATE_DELAY=${UPDATE_DELAY:-1}
CHANGES_DELAY=${CHANGES_DELAY:-10}
CHANGES_LIMIT=${CHANGES_LIMIT:-200}
UP_TIME=${UP_TIME:-86400}

echo "MOBILE_TESTKIT_BRANCH = $MOBILE_TESTKIT_BRANCH"
echo "CBS_HOSTS = $CBS_HOSTS"
echo "COUCHBASE_SERVER_VERSION = $COUCHBASE_SERVER_VERSION"
echo "SGW_HOSTS = $SGW_HOSTS"
echo "SYNC_GATEWAY_VERSION = $SYNC_GATEWAY_VERSION"
echo "COLLECT_LOGS = $COLLECT_LOGS"
echo "SERVER_SEED_DOCS = $SERVER_SEED_DOCS"
echo "MAX_DOCS=$MAX_DOCS"
echo "NUM_USERS = $NUM_USERS"
echo "CREATE_BATCH_SIZE = $CREATE_BATCH_SIZE"
echo "CREATE_DELAY = $CREATE_DELAY"
echo "UPDATE_BATCH_SIZE = $UPDATE_BATCH_SIZE"
echo "UPDATE_DOCS_PERCENTAGE = $UPDATE_DOCS_PERCENTAGE"
echo "UPDATE_DELAY = $UPDATE_DELAY"
echo "CHANGES_DELAY = $CHANGES_DELAY"
echo "CHANGES_LIMIT = $CHANGES_LIMIT"
echo "SSH_USER = $SSH_USER"
echo "SSH_PWD = $SSH_PWD"
echo "UP_TIME = $UP_TIME"

git checkout $MOBILE_TESTKIT_BRANCH
git pull origin $MOBILE_TESTKIT_BRANCH
git fetch
git reset --hard origin/$MOBILE_TESTKIT_BRANCH

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

if [ "$COLLECT_LOGS" == "true" ]; then
	COLLECT_LOGS_FLAG = "--collect-logs"  
else
	COLLECT_LOGS_FLAG = ""
fi

echo "Running system test"
pytest -s -rsx \
  --timeout 864000 \
  --collect-logs=${COLLECT_LOGS} \
  --cbs-endpoints=${CBS_HOSTS} \
  --server-version=${COUCHBASE_SERVER_VERSION} \
  --sgw-endpoints=${SGW_HOSTS} \
  --sync-gateway-version=${SYNC_GATEWAY_VERSION} \
  --server-seed-docs=${SERVER_SEED_DOCS} \
  --max-docs=${MAX_DOCS} \
  --num-users=${NUM_USERS} \
  --create-batch-size=${CREATE_BATCH_SIZE} \
  --create-delay=${CREATE_DELAY} \
  --update-batch-size=${UPDATE_BATCH_SIZE} \
  --update-docs-percentage=${UPDATE_DOCS_PERCENTAGE} \
  --update-delay=${UPDATE_DELAY} \
  --changes-delay=${CHANGES_DELAY} \
  --changes-limit=${CHANGES_LIMIT} \
  --up-time=${UP_TIME} testsuites/syncgateway/system/sequoia/test_system_test.py
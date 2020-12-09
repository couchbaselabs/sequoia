#!/bin/bash

for ARGUMENT in "$@"
do

    KEY=$(echo $ARGUMENT | cut -f1 -d=)
    VALUE=$(echo $ARGUMENT | cut -f2 -d=)   

    case "$KEY" in
            MOBILE_TESTKIT_BRANCH)          MOBILE_TESTKIT_BRANCH=${VALUE} ;;
            SSH_USER)                       SSH_USER=${VALUE} ;;
            SSH_PWD)                        SSH_PWD=${VALUE} ;;
            CBS_HOSTS)                      CBS_HOSTS=${VALUE} ;;
            SGW_HOSTS)                      SGW_HOSTS=${VALUE} ;;
            BUCKET_NAME)                    BUCKET_NAME=${VALUE} ;;
            BUCKET_USER)                    BUCKET_USER=${VALUE} ;;
            BUCKET_USER_PASSWORD)           BUCKET_USER_PASSWORD=${VALUE} ;;
            *)   
    esac    

done

echo "MOBILE_TESTKIT_BRANCH = $MOBILE_TESTKIT_BRANCH"
echo "SSH_USER = $SSH_USER"
echo "SSH_PWD = $SSH_PWD"
echo "CBS_HOSTS = $CBS_HOSTS"
echo "SGW_HOSTS = $SGW_HOSTS"
echo "BUCKET_NAME = $BUCKET_NAME"
echo "BUCKET_USER = $BUCKET_USER"
echo "BUCKET_USER_PASSWORD = $BUCKET_USER_PASSWORD"

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

python utilities/sequoia_cluster_setup.py --cbs-hosts=${CBS_HOSTS} --sgw-hosts=${SGW_HOSTS} --bucket-name=${BUCKET_NAME} --bucket-user=${BUCKET_USER} --bucket-user-pwd=${BUCKET_USER_PASSWORD}
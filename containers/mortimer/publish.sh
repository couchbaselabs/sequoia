#!/bin/bash

HOSTS=$(echo $1 | sed 's/,/\n/g' | tr -d ' ')
REST_USER=$2
REST_PASS=$3
SSH_USER=$4
SSH_PASS=$5

# wait for collection to finish
REST_HOST=$(echo $HOSTS | sed 's/\s.*//')
python wait_for_collection.py $REST_HOST $REST_USER $REST_PASS

if [ $? -eq 0 ]; then
    # collect from each host
    for HOST  in $HOSTS; do
        sshpass -p $SSH_PASS scp -o StrictHostKeyChecking=no $SSH_USER@$HOST:/opt/couchbase/var/lib/couchbase/tmp/collectinfo*.zip .
    done

    python mortimer/mortimer.py
fi

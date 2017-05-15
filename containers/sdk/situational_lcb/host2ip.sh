#!/bin/bash
FILE=$1

CONTAINER_IPS=($(cat /etc/hosts | grep container | awk '{print $1}' | sort))
if [ -n "$SWARM_HOSTS" ]; then
   # override
   CONTAINER_IPS=($(echo $SWARM_HOSTS | sed 's/,/\n/g'))
fi

i=0
for host in $( grep "node \?=" $FILE | awk -F "=" '{print $2}' ); do
  addr=${CONTAINER_IPS[i]}
  services=($(echo $host | grep ":::" | sed "s/.*::://"))
  if [ -n "$services" ]; then
     services=":::"$services
  fi
  echo $host" -> "$addr:8091$services
  sed -i "0,/node.*$host/s//node = $addr:8091$services/" $FILE
  ((i++))
done

#!/bin/bash

available_ram=$(free -g|awk '/^Mem:/{print $7}')
# Catapult max ram usage capped at (available_ram/5)G
# or 2G in case calculation fails
max_limit=$((available_ram / 5))
if [[ "$max_limit" -lt "2" ]]
then
    max_limit=2
fi
max_limit_arg="-Xmx$((max_limit))G"
echo java "$max_limit_arg" -jar javaclient.jar $@
java "$max_limit_arg" -jar javaclient.jar $@
if [[ $? -eq 1 ]]
then
    echo "Catapult exiting because: "
    tail -n 10 java_sdk_loader.log
    exit 1
fi
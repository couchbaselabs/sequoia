#!/bin/bash

echo java -jar javaclient.jar $@
java -jar javaclient.jar $@
if [[ $? -eq 1 ]]
then
    echo "Catapult exiting because: "
    tail -n 10 java_sdk_loader.log
    exit 1
fi
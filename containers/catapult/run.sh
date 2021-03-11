#!/bin/bash

echo java -Xms2G -Xmx2G -jar javaclient.jar $@
java -Xms2G -Xmx2G -jar javaclient.jar $@
if [[ $? -eq 1 ]]
then
    echo "Catapult exiting because: "
    tail -n 10 java_sdk_loader.log
    exit 1
fi
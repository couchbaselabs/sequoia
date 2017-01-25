#!/bin/bash
SDK_COMMIT_SHA=${1:-master}

# build sdk 
docker build --build-arg COMMIT=$SDK_COMMIT_SHA -t  sequoiatools/sdk-java-client java-client 
docker build -t  sequoiatools/sdk-java-resource java-resource

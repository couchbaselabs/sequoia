#!/bin/bash

host=$1:8091
Auth=$2
Engine=${3:-memory_optimized}
Uri=http://$Auth@$host/settings/indexes

echo curl -vv -X POST $Uri -d "storageMode=$Engine"
curl -v -X POST $Uri -d "storageMode=$Engine"

#!/bin/bash

host=$1:8091
Engine=memory_optimized
Auth=$2
Uri=http://$Auth@$host/settings/indexes

echo curl -vv -X POST $Uri -d "storageMode=$Engine"
curl -v -X POST $Uri -d "storageMode=$Engine"

#!/bin/bash

host=$1:9108
Engine=memory_optimized
Auth=$2
Uri=http://$Auth@$host/settings

curl -X POST  $Uri --data '{"indexer.settings.storage_mode" : "$Engine"}'
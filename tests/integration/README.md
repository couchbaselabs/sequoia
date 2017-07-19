The longevity test combines query, search, views, xdcr, and mobile services into a single test under a constant data load with lots of changes to cluster topology.  Current cluster scale is 7 data nodes, 3 index nodes, 2 query nodes, 2 fts nodes, 1 sync gateway.

 To run and repro:
```bash
# build
go get github.com/couchbaselabs/sequoia
go build

# CHANGE * the IP's inside the provider file to match your own (see providers/file/ubuntu_172-23-106.yml)
         * the client to be your docker client
./sequoia -client 172.23.108.94:2375 -provider file:centos_pine.yml -test tests/integration/test_allFeaturesWithReplica.yml -scope tests/integration/scope_ReplicaIndex.yml -scale 3 -repeat 0 -log_level 0 -version 5.0.0-1004 -skip_setup=false -skip_test=false -skip_teardown=true -skip_cleanup=false -continue=false -collect_on_error=true -stop_on_error=false -duration=0
```


The test will execute the following series of operations.  But first, here's an example of how to interpret each line of output from the test:

```bash
[2017-07-16T09:34:25-07:00, sequoiatools/pillowfight:9b4ae1] -U couchbase://172.23.108.103/default?select_bucket=true -M 512 -I 2000 -B 200 -t 1 --rate-limit 2000 -P password
 ```

Is equivalent to running the following docker command:
```bash
docker run sequoiatools/pillowfight -U couchbase://172.23.106.14/default?select_bucket=true -I 5000 -B 500 -t 4 -c 100 -P password
 ```

Our longevity test will loop the following steps for 7 days:
```bash
[2017-07-16T09:34:25-07:00, sequoiatools/pillowfight:9b4ae1] -U couchbase://172.23.108.103/default?select_bucket=true -M 512 -I 2000 -B 200 -t 1 --rate-limit 2000 -P password
[2017-07-16T09:35:32-07:00, sequoiatools/couchbase-cli:4135c2] rebalance -c 172.23.108.103:8091 --server-remove 172.23.108.104:8091 -u Administrator -p password
[2017-07-16T09:51:12-07:00, sequoiatools/cmd:ba4859] 60
[2017-07-16T09:53:27-07:00, sequoiatools/cbq:a9d51a] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index default_rating on `default`(rating) using GSI with {"num_replica":1}
[2017-07-16T09:55:03-07:00, sequoiatools/cbq:4d0a2b] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index default_claims on `default`(claim) using GSI with {"num_replica":2}
[2017-07-16T09:57:16-07:00, sequoiatools/cbq:8fd2c1] -e=http://172.23.99.25:8093 -u=Administrator -p=password
[2017-07-16T09:57:24-07:00, sequoiatools/cbq:32f036] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create primary index on `default` using GSI with {"num_replica":2}
[2017-07-16T09:59:42-07:00, sequoiatools/cbq:1418c5] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o1_rating on `CUSTOMER`(rating) using GSI with {"num_replica":2}
[2017-07-16T10:00:09-07:00, sequoiatools/cbq:bfe04d] -e=http://172.23.99.25:8093 -u=Administrator -p=password
[2017-07-16T10:00:16-07:00, sequoiatools/cbq:1aae3c] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o1_result on `CUSTOMER`(result) using GSI with {"num_replica":1}
[2017-07-16T10:00:45-07:00, sequoiatools/cbq:78ec39] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o2_rating on `DISTRICT`(rating) using GSI with {"num_replica":2}
[2017-07-16T10:01:11-07:00, sequoiatools/cbq:9e25b9] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o2_claims on `DISTRICT`(claim) using GSI with {"num_replica":1}
[2017-07-16T10:01:37-07:00, sequoiatools/cbq:8f04ea] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o2_result on `DISTRICT`(result) using GSI with {"num_replica":2}
[2017-07-16T10:02:01-07:00, sequoiatools/cbq:fdf252] -e=http://172.23.99.25:8093 -u=Administrator -p=password
[2017-07-16T10:02:10-07:00, sequoiatools/cbq:f5cb5b] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o3_claims on `HISTORY`(claim) using GSI with {"num_replica":1}
[2017-07-16T10:02:32-07:00, sequoiatools/cbq:613b79] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o3_result on `HISTORY`(result) using GSI with {"num_replica":2}
[2017-07-16T10:02:55-07:00, sequoiatools/cbq:96b3ff] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=build index on `default`(result)
[2017-07-16T10:03:04-07:00, sequoiatools/cbq:5a1436] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=build index on `HISTORY`(rating)
[2017-07-16T10:03:11-07:00, sequoiatools/cbq:e15aae] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=build index on `HISTORY`(rating)
[2017-07-16T10:03:19-07:00, sequoiatools/gideon:030b5b] kv --ops 500 --create 10 --delete 8 --get 82 --sizes 64 96 --expire 100 --ttl 3600 --hosts 172.23.108.103 --bucket CUSTOMER
[2017-07-16T10:03:24-07:00, sequoiatools/gideon:3e24b8] kv --ops 500 --create 10 --delete 8 --get 82 --sizes 64 96 --expire 100 --ttl 3600 --hosts 172.23.108.103 --bucket DISTRICT
[2017-07-16T10:03:30-07:00, sequoiatools/gideon:d4a489] kv --ops 500 --create 10 --delete 8 --get 82 --sizes 64 96 --expire 100 --ttl 3600 --hosts 172.23.108.103 --bucket HISTORY
[2017-07-16T10:03:35-07:00, sequoiatools/cbdozer:8e68d8] -method POST -duration 0 -rate 3 -url http://Administrator:password@172.23.99.25:8093/query/service -body select SUM(result) from default where result > 0 limit 50
[2017-07-16T10:03:42-07:00, sequoiatools/cbdozer:f1ea44] -method POST -duration 0 -rate 3 -url http://Administrator:password@172.23.99.25:8093/query/service -body select claim from default where result > 0 limit 50
[2017-07-16T10:03:46-07:00, sequoiatools/cbdozer:9a4118] -method POST -duration 0 -rate 3 -url http://Administrator:password@172.23.99.25:8093/query/service -body select SUM(result) from `CUSTOMER` where result > 100 limit 50
[2017-07-16T10:03:50-07:00, sequoiatools/cbdozer:b5576a] -method POST -duration 0 -rate 3 -url http://Administrator:password@172.23.99.25:8093/query/service -body select * from `CUSTOMER` where result > 100 limit 50
[2017-07-16T10:03:55-07:00, sequoiatools/cbdozer:70a1d9] -method POST -duration 0 -rate 3 -url http://Administrator:password@172.23.99.25:8093/query/service -body select SUM(result) from `DISTRICT` where claim like c% limit 50
[2017-07-16T10:04:01-07:00, sequoiatools/cbdozer:207a04] -method POST -duration 0 -rate 3 -url http://Administrator:password@172.23.99.25:8093/query/service -body select SUM(result) from `HISTORY` where rating like a% limit 20
[2017-07-16T10:05:24-07:00, sequoiatools/couchbase-cli:d143fa] server-add -c 172.23.108.103:8091 --server-add 172.23.108.104:8091 -u Administrator -p password --server-add-username Administrator --server-add-password password --services data
[2017-07-16T10:05:41-07:00, sequoiatools/couchbase-cli:0d0494] rebalance -c 172.23.108.103:8091 --server-remove 172.23.98.135 -u Administrator -p password
[2017-07-16T10:25:24-07:00, sequoiatools/cmd:b579f5] 60
[2017-07-16T10:27:56-07:00, sequoiatools/cbdozer:4ebe51] -method POST -duration 0 -rate 10 -url http://Administrator:password@172.23.107.47:8093/query/service -body delete from default where rating > 0 limit 10
[2017-07-16T10:28:00-07:00, sequoiatools/cbdozer:5309a6] -method POST -duration 0 -rate 5 -url http://Administrator:password@172.23.107.47:8093/query/service -body select * from default where rating > 100 limit 10 offset 0
[2017-07-16T10:28:06-07:00, sequoiatools/cbdozer:40bf79] -method POST -duration 0 -rate 5 -url http://Administrator:password@172.23.107.47:8093/query/service -body select * from default where rating > 100 limit 10 offset 100
[2017-07-16T10:28:09-07:00, sequoiatools/cbdozer:346512] -method POST -duration 0 -rate 5 -url http://Administrator:password@172.23.107.47:8093/query/service -body select * from default where rating > 100 limit 10 offset 200
[2017-07-16T10:28:15-07:00, sequoiatools/cbdozer:0e208f] -method POST -duration 0 -rate 5 -url http://Administrator:password@172.23.107.47:8093/query/service -body select * from default where rating > 100 limit 10 offset 300
[2017-07-16T10:28:20-07:00, sequoiatools/cbdozer:4601b6] -method POST -duration 0 -rate 5 -url http://Administrator:password@172.23.107.47:8093/query/service -body select * from default where rating > 100 limit 10 offset 400
[2017-07-16T10:28:26-07:00, sequoiatools/cbdozer:23c105] -method POST -duration 0 -rate 5 -url http://Administrator:password@172.23.107.47:8093/query/service -body select * from default where rating > 100 limit 10 offset 500
[2017-07-16T10:28:30-07:00, sequoiatools/gideon:78af0a] kv --ops 500 --create 10 --delete 8 --get 92 --expire 100 --ttl 660 --hosts 172.23.108.103 --bucket default --sizes 512 128 1024 2048 16000
[2017-07-16T10:28:36-07:00, sequoiatools/gideon:e5861a] kv --ops 500 --create 100 --expire 100 --ttl 660 --hosts 172.23.108.103 --bucket default --sizes 64
[2017-07-16T10:28:40-07:00, sequoiatools/gideon:9a0df2] kv --ops 600 --create 15 --get 80 --delete 5 --expire 100 --ttl 660 --hosts 172.23.108.103 --bucket default --sizes 128
[2017-07-16T10:28:46-07:00, danihodovic/vegeta:c3769e] bash -c echo GET "http://Administrator:password@172.23.108.103:8092/default/_design/scale/_view/stats?limit=10&stale=update_after&connection_timeout=60000" | vegeta attack -duration=0 -rate=10> results.bin && vegeta report -inputs=results.bin > results.txt && vegeta report -inputs=results.bin -reporter=plot > plot.html
[2017-07-16T10:28:49-07:00, danihodovic/vegeta:85800f] bash -c echo GET "http://Administrator:password@172.23.108.104:8092/default/_design/scale/_view/array?limit=10&stale=update_after&connection_timeout=60000" | vegeta attack -duration=0 -rate=10> results.bin && vegeta report -inputs=results.bin > results.txt && vegeta report -inputs=results.bin -reporter=plot > plot.html
[2017-07-16T10:28:57-07:00, danihodovic/vegeta:d12fd5] bash -c echo GET "http://Administrator:password@172.23.98.135:8092/default/_design/scale/_view/padd?limit=10&stale=update_after&connection_timeout=60000" | vegeta attack -duration=0 -rate=10> results.bin && vegeta report -inputs=results.bin > results.txt && vegeta report -inputs=results.bin -reporter=plot > plot.html
[2017-07-16T10:29:02-07:00, sequoiatools/couchbase-cli:221187] rebalance -c 172.23.108.103:8091 --server-remove 172.23.108.107 -u Administrator -p password
[2017-07-16T10:30:19-07:00, sequoiatools/cmd:bd9185] 60
[2017-07-16T10:33:25-07:00, appropriate/curl:f7aad2] -X PUT -u Administrator:password -H Content-Type:application/json http://172.23.106.188:8094/api/index/good_state -d { "type": "fulltext-index","name": "SUCCESS","sourceType": "couchbase","sourceName": "default","planParams": { "maxPartitionsPerPIndex": 171 },"params": { "doc_config": { "mode": "type_field","type_field": "result" },"mapping": { "default_mapping": { "enabled": false },"index_dynamic": true,"store_dynamic": false,"types": { "SUCCESS": { "dynamic": false,"enabled": true,"properties": { "state": { "dynamic": false,"enabled": true,"fields": [ { "analyzer": "","include_in_all": true,"include_term_vectors": true,"index": true,"name": "state","store": false,"type": "text" } ] } } } } },"store": { "kvStoreName": "mossStore" } },"sourceParams": {} }
[2017-07-16T10:33:35-07:00, appropriate/curl:e5eda2] -X PUT -u Administrator:password -H Content-Type:application/json http://172.23.106.188:8094/api/index/social -d { "type": "fulltext-index","name": "gideon","sourceType": "couchbase","sourceName": "default","planParams": { "maxPartitionsPerPIndex": 171 },"params": { "doc_config": { "mode": "type_field","type_field": "type" },"mapping": { "default_mapping": { "enabled": false },"index_dynamic": true,"store_dynamic": false,"types": { "gideon": { "dynamic": false,"enabled": true,"properties": { "description": { "dynamic": false,"enabled": true,"fields": [ { "analyzer": "","include_in_all": true,"include_term_vectors": true,"index": true,"name": "description","store": true,"type": "text" } ] },"profile": { "dynamic": false,"enabled": true,"properties": { "status": { "dynamic": false,"enabled": true,"fields": [ { "analyzer": "","include_in_all": true,"include_term_vectors": true,"index": true,"name": "status","store": true,"type": "text" } ] } } } } } } },"store": { "kvStoreName": "mossStore" } },"sourceParams": {} }
[2017-07-16T10:33:38-07:00, sequoiatools/cbdozer:db88ef] fts -method POST -duration -1 -rate 3 -url http://Administrator:password@172.23.106.188:8094/api/index/good_state/query -query +state:9C -size 10
[2017-07-16T10:33:43-07:00, sequoiatools/cbdozer:301b4c] fts -method POST -duration -1 -rate 3 -url http://Administrator:password@172.23.106.188:8094/api/index/social/query -query +profile.status:4121* -size 10
[2017-07-16T10:33:50-07:00, sequoiatools/couchbase-cli:79f4f8] user-manage -c 172.23.108.103 -u Administrator -p password --rbac-username queryUser1 --rbac-password password1 --roles query_select[default] --auth-domain local --set
[2017-07-16T10:33:56-07:00, sequoiatools/couchbase-cli:2f227e] user-manage -c 172.23.108.103 -u Administrator -p password --rbac-username queryUser2 --rbac-password password2 --roles query_select[default],query_insert[default] --auth-domain local --set
[2017-07-16T10:34:00-07:00, sequoiatools/couchbase-cli:577ae4] user-manage -c 172.23.108.103 -u Administrator -p password --rbac-username queryUser3 --rbac-password password3 --roles query_update[default] --auth-domain local --set
[2017-07-16T10:34:05-07:00, sequoiatools/couchbase-cli:c2493f] user-manage -c 172.23.108.103 -u Administrator -p password --rbac-username queryUser4 --rbac-password password4 --roles query_delete[default] --auth-domain local --set
[2017-07-16T10:34:12-07:00, sequoiatools/couchbase-cli:41ee74] user-manage -c 172.23.108.103 -u Administrator -p password --rbac-username queryUser5 --rbac-password password5 --roles query_manage_index[default] --auth-domain local --set
[2017-07-16T10:34:18-07:00, sequoiatools/cbq:afcbad] -e=http://172.23.99.25:8093 -u=queryUser2 -p=password2 -script=insert into `default`(KEY claim, VALUE rating) SELECT claim, rating from `default` WHERE rating > 300 limit 10
[2017-07-16T10:34:21-07:00, sequoiatools/cbdozer:54d50b] -method POST -duration 0 -rate 3 -url http://queryUser1:password1@172.23.99.25:8093/query/service -body select * from `default` where result="SUCCESS" limit 20
[2017-07-16T10:34:26-07:00, sequoiatools/cbdozer:2e589a] -method POST -duration 0 -rate 3 -url http://queryUser3:password3@172.23.107.47:8093/query/service -body update `default` set name = "test" WHERE claim is not missing limit 10
[2017-07-16T10:34:31-07:00, sequoiatools/cbdozer:3d7336] -method POST -duration 0 -rate 3 -url http://queryUser4:password4@172.23.99.25:8093/query/service -body delete from `default` where rating < 700 limit 20
[2017-07-16T10:34:38-07:00, sequoiatools/cbq:0214ed] -e=http://172.23.99.25:8093 -u=queryUser5 -p=password5 -script=create index usr5_city_idx on `default`(city)
[2017-07-16T10:34:42-07:00, sequoiatools/pillowfight:d1bd08] -U couchbase://172.23.108.103/default?select_bucket=true -I 1000 -B 100 -t 4 -c 100 -P password
[2017-07-16T10:34:53-07:00, sequoiatools/cbq:bd31f5] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=drop index `default`
[2017-07-16T10:36:57-07:00, sequoiatools/cbq:07fa4e] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=drop index `default`.default_rating
[2017-07-16T10:39:04-07:00, sequoiatools/cbq:89b7c9] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=drop index `CUSTOMER`.o1_rating
[2017-07-16T10:41:10-07:00, sequoiatools/cbq:d31b42] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=drop index `CUSTOMER`.o1_claims
[2017-07-16T10:43:13-07:00, sequoiatools/cbq:845903] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=drop index `DISTRICT`.o2_results
[2017-07-16T10:45:16-07:00, sequoiatools/cbq:09c942] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=drop index `HISTORY`.o3_rating
[2017-07-16T10:47:19-07:00, sequoiatools/cbq:611e77] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=drop index `HISTORY`.o3_results
[2017-07-16T10:49:20-07:00, sequoiatools/cbq:128700] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index default_claims on `default`(claim) using GSI
[2017-07-16T10:51:22-07:00, sequoiatools/cbq:0656ee] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create primary index on `default` using GSI
[2017-07-16T10:53:25-07:00, sequoiatools/cbq:33ea1d] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o1_result on `CUSTOMER`(result) using GSI
[2017-07-16T10:55:28-07:00, sequoiatools/cbq:c3c989] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o2_claims on `DISTRICT`(claim) using GSI
[2017-07-16T10:57:32-07:00, sequoiatools/cbq:e19d14] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o3_claims on `HISTORY`(claim) using GSI
[2017-07-16T11:01:08-07:00, sequoiatools/couchbase-cli:b3c71c] server-add -c 172.23.108.103:8091 --server-add 172.23.108.107:8091 -u Administrator -p password --server-add-username Administrator --server-add-password password --services index
[2017-07-16T11:01:22-07:00, sequoiatools/couchbase-cli:41b179] rebalance -c 172.23.108.103:8091 -u Administrator -p password
[2017-07-16T11:05:54-07:00, sequoiatools/cmd:b5ec39] 60
[2017-07-16T11:08:59-07:00, sequoiatools/couchbase-cli:26f086] rebalance -c 172.23.108.103:8091 --server-remove 172.23.108.107 -u Administrator -p password
[2017-07-16T11:09:22-07:00, sequoiatools/cmd:621b42] 60
[2017-07-16T11:13:32-07:00, sequoiatools/couchbase-cli:61a31e] server-add -c 172.23.108.103:8091 --server-add 172.23.108.107:8091 -u Administrator -p password --server-add-username Administrator --server-add-password password --services index
[2017-07-16T11:13:47-07:00, sequoiatools/couchbase-cli:32a5e1] rebalance -c 172.23.108.103:8091 --server-remove 172.23.97.237 -u Administrator -p password
[2017-07-16T11:19:38-07:00, sequoiatools/cmd:580d0c] 60
[2017-07-16T11:22:17-07:00, sequoiatools/couchbase-cli:dc9518] server-add -c 172.23.108.103:8091 --server-add 172.23.98.135:8091 -u Administrator -p password --server-add-username Administrator --server-add-password password --services index
[2017-07-16T11:22:30-07:00, sequoiatools/couchbase-cli:8d921a] server-add -c 172.23.108.103:8091 --server-add 172.23.97.237:8091 -u Administrator -p password --server-add-username Administrator --server-add-password password --services index
[2017-07-16T11:22:43-07:00, sequoiatools/couchbase-cli:d05dbf] rebalance -c 172.23.108.103:8091 -u Administrator -p password
[2017-07-16T11:26:35-07:00, sequoiatools/cmd:5a9f5b] 60
[2017-07-16T11:29:35-07:00, sequoiatools/couchbase-cli:cbdd6f] rebalance -c 172.23.108.103:8091 --server-remove 172.23.108.107,172.23.97.237 -u Administrator -p password
[2017-07-16T11:33:15-07:00, sequoiatools/cmd:3829f0] 60
[2017-07-16T11:35:55-07:00, sequoiatools/couchbase-cli:4b8ff9] server-add -c 172.23.108.103:8091 --server-add 172.23.108.107:8091 -u Administrator -p password --server-add-username Administrator --server-add-password password --services index
[2017-07-16T11:36:11-07:00, sequoiatools/couchbase-cli:76076f] server-add -c 172.23.108.103:8091 --server-add 172.23.97.237:8091 -u Administrator -p password --server-add-username Administrator --server-add-password password --services index
[2017-07-16T11:37:58-07:00, sequoiatools/couchbase-cli:23728e] rebalance -c 172.23.108.103:8091 --server-remove 172.23.108.104 -u Administrator -p password
[2017-07-16T12:00:00-07:00, sequoiatools/cmd:ff274d] 60
[2017-07-16T12:02:49-07:00, sequoiatools/couchbase-cli:d55e25] server-add -c 172.23.108.103:8091 --server-add 172.23.108.104:8091 -u Administrator -p password --server-add-username Administrator --server-add-password password --services data
[2017-07-16T12:03:06-07:00, sequoiatools/couchbase-cli:ab8e59] rebalance -c 172.23.108.103:8091 -u Administrator -p password
[2017-07-16T12:24:51-07:00, sequoiatools/cmd:baf4b4] 60
[2017-07-16T12:27:40-07:00, sequoiatools/couchbase-cli:4adddb] failover -c 172.23.108.103:8091 --server-failover 172.23.97.237:8091 -u Administrator -p password --force
[2017-07-16T12:27:51-07:00, sequoiatools/couchbase-cli:b1574a] recovery -c 172.23.108.103:8091 --server-recovery 172.23.97.237:8091 --recovery-type full -u Administrator -p password
[2017-07-16T12:27:57-07:00, sequoiatools/couchbase-cli:906471] rebalance -c 172.23.108.103:8091 -u Administrator -p password
[2017-07-16T12:28:27-07:00, sequoiatools/cmd:9557fe] 60
[2017-07-16T12:31:34-07:00, sequoiatools/couchbase-cli:61f315] failover -c 172.23.108.103:8091 --server-failover 172.23.98.135:8091 -u Administrator -p password --force
[2017-07-16T12:31:46-07:00, sequoiatools/couchbase-cli:946ff8] rebalance -c 172.23.108.103:8091 -u Administrator -p password
[2017-07-16T12:37:57-07:00, sequoiatools/cmd:db9d48] 60
[2017-07-16T12:40:59-07:00, sequoiatools/couchbase-cli:e33a94] rebalance -c 172.23.108.103:8091 --server-remove 172.23.97.238 -u Administrator -p password
[2017-07-16T12:47:28-07:00, sequoiatools/cmd:7316b8] 60
[2017-07-16T12:50:06-07:00, sequoiatools/couchbase-cli:68056a] server-add -c 172.23.108.103:8091 --server-add 172.23.98.135:8091 -u Administrator -p password --server-add-username Administrator --server-add-password password --services index
[2017-07-16T12:50:20-07:00, sequoiatools/couchbase-cli:ca8cd2] server-add -c 172.23.108.103:8091 --server-add 172.23.97.238:8091 -u Administrator -p password --server-add-username Administrator --server-add-password password --services index
[2017-07-16T12:50:34-07:00, sequoiatools/couchbase-cli:fd2898] rebalance -c 172.23.108.103:8091 -u Administrator -p password
[2017-07-16T12:50:38-07:00, sequoiatools/cmd:ba13f7] 60
[2017-07-16T12:53:17-07:00, sequoiatools/tpcc:72ffd6] python tpcc.py --duration 259200 --client 1 --warehouses 5 --no-execute n1ql --query-url 172.23.99.25:8093 --userid Administrator --password password
[2017-07-16T12:54:57-07:00, sequoiatools/tpcc:b26049] python tpcc.py --duration 2259200 --client 1 --warehouses 5 --no-load n1ql --query-url 172.23.107.47:8093
[2017-07-16T12:57:46-07:00, sequoiatools/couchbase-cli:3aa036] rebalance -c 172.23.108.103:8091 --server-remove 172.23.108.107 -u Administrator -p password
[2017-07-16T13:06:10-07:00, sequoiatools/cmd:bdf4ff] 60
[2017-07-16T13:07:20-07:00, sequoiatools/pillowfight:52d3ec] -U couchbase://172.23.108.103/default?select_bucket=true -I 1000 -B 100 -t 4 -c 100 -P password
[2017-07-16T13:09:07-07:00, sequoiatools/couchbase-cli:2f1c90] server-add -c 172.23.108.103:8091 --server-add 172.23.108.107:8091 -u Administrator -p password --server-add-username Administrator --server-add-password password --services data
[2017-07-16T13:11:01-07:00, sequoiatools/couchbase-cli:d328e0] failover -c 172.23.108.103:8091 --server-failover 172.23.108.104:8091 -u Administrator -p password --force
[2017-07-16T13:11:17-07:00, sequoiatools/couchbase-cli:0065e3] rebalance -c 172.23.108.103:8091 -u Administrator -p password
[2017-07-16T13:30:48-07:00, sequoiatools/cmd:f5a2e6] 60
[2017-07-16T13:31:57-07:00, sequoiatools/gideon:47f8c7] kv --ops 500 --create 100 --expire 100 --ttl 660 --hosts 172.23.108.103 --bucket default --sizes 64
[2017-07-16T13:32:03-07:00, sequoiatools/pillowfight:bce7ef] -U couchbase://172.23.108.103/default?select_bucket=true -I 1000 -B 100 -t 4 -c 100 -P password
[2017-07-16T13:33:56-07:00, sequoiatools/couchbase-cli:0acd09] server-add -c 172.23.108.103:8091 --server-add 172.23.108.104:8091 -u Administrator -p password --server-add-username Administrator --server-add-password password --services data
[2017-07-16T13:35:59-07:00, sequoiatools/couchbase-cli:2c6fc7] failover -c 172.23.108.103:8091 --server-failover 172.23.108.107:8091 -u Administrator -p password
[2017-07-16T13:47:28-07:00, sequoiatools/couchbase-cli:875465] failover -c 172.23.108.103:8091 --server-failover 172.23.97.239:8091 -u Administrator -p password --force
[2017-07-16T13:47:44-07:00, sequoiatools/couchbase-cli:6614a4] rebalance -c 172.23.108.103:8091 -u Administrator -p password
[2017-07-16T14:25:00-07:00, sequoiatools/cmd:ffc592] 60
[2017-07-16T14:27:50-07:00, sequoiatools/couchbase-cli:c8964a] setting-autofailover -c 172.23.108.103:8091 -u Administrator -p password --enable-auto-failover=1 --auto-failover-timeout=5
[2017-07-16T14:28:02-07:00, vijayviji/sshpass:cbaecf] sshpass -p couchbase ssh -o StrictHostKeyChecking=no root@172.23.108.104 kill -SIGSTOP $(pgrep memcached)
[2017-07-16T14:28:17-07:00, vijayviji/sshpass:52622d] sshpass -p couchbase ssh -o StrictHostKeyChecking=no root@172.23.108.104 kill -SIGCONT $(pgrep memcached)
[2017-07-16T14:28:32-07:00, sequoiatools/couchbase-cli:456f58] recovery -c 172.23.108.103:8091 --server-recovery 172.23.108.104:8091 --recovery-type full -u Administrator -p password
[2017-07-16T14:28:41-07:00, sequoiatools/couchbase-cli:d34984] rebalance -c 172.23.108.103:8091 -u Administrator -p password
[2017-07-16T14:59:45-07:00, sequoiatools/cmd:c99c3b] 60
[2017-07-16T15:00:54-07:00, sequoiatools/couchbase-cli:35719e] setting-autofailover -c 172.23.108.103:8091 -u Administrator -p password --enable-auto-failover=0
[2017-07-16T15:01:03-07:00, sequoiatools/pillowfight:c57fcf] -U couchbase://172.23.108.103/default?select_bucket=true -I 1000 -B 100 -t 4 -c 100 -P password
[2017-07-16T15:02:58-07:00, sequoiatools/couchbase-cli:7214e3] rebalance -c 172.23.108.103:8091 --server-remove 172.23.98.135 -u Administrator -p password
[2017-07-16T15:04:11-07:00, sequoiatools/cmd:251fd3] 60
[2017-07-16T15:07:15-07:00, sequoiatools/cbq:30d0c1] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index default_rating on `default`(rating)
[2017-07-16T15:12:00-07:00, sequoiatools/cbq:bea961] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index default_result on `default`(result)
[2017-07-16T15:16:21-07:00, sequoiatools/cbq:95f1f3] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create primary index on `default`
[2017-07-16T15:18:10-07:00, sequoiatools/cbq:3a1452] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o1_rating on `CUSTOMER`(rating)
[2017-07-16T15:20:21-07:00, sequoiatools/cbq:c9cf12] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o1_claims on `CUSTOMER`(claim)
[2017-07-16T15:22:33-07:00, sequoiatools/cbq:dea6f3] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o1_result on `CUSTOMER`(result)
[2017-07-16T15:24:24-07:00, sequoiatools/cbq:20efe7] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o2_rating on `DISTRICT`(rating)
[2017-07-16T15:26:14-07:00, sequoiatools/cbq:b1049e] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o2_claims on `DISTRICT`(claim)
[2017-07-16T15:28:03-07:00, sequoiatools/cbq:06483c] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o2_result on `DISTRICT`(result)
[2017-07-16T15:29:53-07:00, sequoiatools/cbq:ae600e] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o3_rating on `HISTORY`(rating)
[2017-07-16T15:32:05-07:00, sequoiatools/cbq:d86286] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o3_claims on `HISTORY`(claim)
[2017-07-16T15:33:56-07:00, sequoiatools/cbq:19a572] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o3_result on `HISTORY`(result)
[2017-07-16T15:35:47-07:00, sequoiatools/cbdozer:ced0da] -method POST -duration 0 -rate 10 -url http://Administrator:password@172.23.99.25:8093/query/service -body select * from default where rating > 0 limit 50
[2017-07-16T15:35:50-07:00, sequoiatools/cbdozer:d2a62d] -method POST -duration 0 -rate 10 -url http://Administrator:password@172.23.99.25:8093/query/service -body select * from `CUSTOMER` where rating > 100 limit 50
[2017-07-16T15:35:55-07:00, sequoiatools/cbdozer:ff8c04] -method POST -duration 0 -rate 10 -url http://Administrator:password@172.23.99.25:8093/query/service -body select SUM(rating) from `DISTRICT` where result = SUCCESS limit 50
[2017-07-16T15:36:02-07:00, sequoiatools/cbdozer:fc6e67] -method POST -duration 0 -rate 10 -url http://Administrator:password@172.23.99.25:8093/query/service -body select SUM(rating) from `HISTORY` where claim like A% limit 20
[2017-07-16T15:36:05-07:00, sequoiatools/cbdozer:2d6bad] -method POST -duration 0 -rate 10 -url http://Administrator:password@172.23.99.25:8093/query/service -body delete from default where rating < 300
[2017-07-16T15:36:11-07:00, sequoiatools/cbdozer:82e730] -method POST -duration 0 -rate 10 -url http://Administrator:password@172.23.99.25:8093/query/service -body delete from default where rating > 700
[2017-07-16T15:36:14-07:00, sequoiatools/cbdozer:351611] -method POST -duration 0 -rate 10 -url http://Administrator:password@172.23.99.25:8093/query/service -body delete from default where rating > 300 and rating < 700
[2017-07-16T15:38:15-07:00, sequoiatools/couchbase-cli:dd458d] server-add -c 172.23.108.103:8091 --server-add 172.23.108.107:8091 -u Administrator -p password --server-add-username Administrator --server-add-password password --services index
[2017-07-16T15:38:30-07:00, sequoiatools/couchbase-cli:124c93] rebalance -c 172.23.108.103:8091 --server-remove 172.23.97.237 -u Administrator -p password
[2017-07-16T15:38:37-07:00, sequoiatools/cmd:2f71e7] 60
[2017-07-16T15:41:43-07:00, sequoiatools/cbq:fdd1cb] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=drop index `default`
[2017-07-16T15:45:46-07:00, sequoiatools/cbq:6c0acc] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=drop index `CUSTOMER`.o1_rating
[2017-07-16T15:47:39-07:00, sequoiatools/cbq:41a745] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=drop index `DISTRICT`.o2_rating
[2017-07-16T15:47:55-07:00, sequoiatools/cbq:0f2417] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=drop index `HISTORY`.o3_rating
[2017-07-16T15:48:10-07:00, sequoiatools/cbq:ea3678] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create primary index on `default`
[2017-07-16T15:48:21-07:00, sequoiatools/cbq:8dd917] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o3_rating on `HISTORY`(rating)
[2017-07-16T15:48:56-07:00, sequoiatools/cbq:eb5521] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=drop index `DISTRICT`.o2_claims
[2017-07-16T15:49:15-07:00, sequoiatools/cbq:af3d68] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=drop index `HISTORY`.o3_claims
[2017-07-16T15:49:29-07:00, sequoiatools/couchbase-cli:3d7e11] failover -c 172.23.108.103:8091 --server-failover 172.23.108.107:8091 -u Administrator -p password --force
[2017-07-16T15:51:55-07:00, sequoiatools/couchbase-cli:0befd1] server-add -c 172.23.108.103:8091 --server-add 172.23.98.135:8091 -u Administrator -p password --server-add-username Administrator --server-add-password password --services data
[2017-07-16T15:52:09-07:00, sequoiatools/couchbase-cli:a60dfc] rebalance -c 172.23.108.103:8091 -u Administrator -p password
[2017-07-16T16:09:55-07:00, sequoiatools/cmd:ef65db] 60
[2017-07-16T16:13:14-07:00, sequoiatools/cbq:6d7155] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index default_rating on `default`(rating)
[2017-07-16T16:13:25-07:00, sequoiatools/cbq:542c59] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index default_claims on `default`(claim)
[2017-07-16T16:13:38-07:00, sequoiatools/cbq:ca96a9] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index default_result on `default`(result)
[2017-07-16T16:13:49-07:00, sequoiatools/cbq:cbb86e] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create primary index on `default`
[2017-07-16T16:13:58-07:00, sequoiatools/cbq:09bb5e] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o1_rating on `CUSTOMER`(rating)
[2017-07-16T16:14:29-07:00, sequoiatools/cbq:81d2a7] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o1_claims on `CUSTOMER`(claim)
[2017-07-16T16:14:40-07:00, sequoiatools/cbq:85030e] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o1_result on `CUSTOMER`(result)
[2017-07-16T16:14:51-07:00, sequoiatools/cbq:6958f4] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o2_rating on `DISTRICT`(rating)
[2017-07-16T16:15:24-07:00, sequoiatools/cbq:8a06b9] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o2_claims on `DISTRICT`(claim)
[2017-07-16T16:15:54-07:00, sequoiatools/cbq:8abada] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o2_result on `DISTRICT`(result)
[2017-07-16T16:16:03-07:00, sequoiatools/cbq:6eac25] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o3_rating on `HISTORY`(rating)
[2017-07-16T16:16:35-07:00, sequoiatools/cbq:5cd11f] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o3_claims on `HISTORY`(claim)
[2017-07-16T16:17:07-07:00, sequoiatools/cbq:d24f71] -e=http://172.23.99.25:8093 -u=Administrator -p=password -script=create index o3_result on `HISTORY`(result)
[2017-07-16T16:17:18-07:00, sequoiatools/pillowfight:d89f0f] -U couchbase://172.23.108.103/default?select_bucket=true -M 512 -I 2000 -B 200 -t 4 --rate-limit 2000 -P password
[2017-07-16T16:27:34-07:00, sequoiatools/couchbase-cli:c37084] failover -c 172.23.108.103:8091 --server-failover 172.23.97.238:8091 -u Administrator -p password --force
[2017-07-16T16:30:07-07:00, sequoiatools/couchbase-cli:9b1236] server-add -c 172.23.108.103:8091 --server-add 172.23.108.107:8091 -u Administrator -p password --server-add-username Administrator --server-add-password password --services index
[2017-07-16T16:30:25-07:00, sequoiatools/couchbase-cli:48b012] rebalance -c 172.23.108.103:8091 -u Administrator -p password
[2017-07-16T16:30:47-07:00, sequoiatools/cmd:4b496c] 60
[2017-07-16T16:34:06-07:00, sequoiatools/couchbase-cli:2a92b7] server-add -c 172.23.108.103:8091 --server-add 172.23.97.237:8091 -u Administrator -p password --server-add-username Administrator --server-add-password password --services index
[2017-07-16T16:34:20-07:00, sequoiatools/couchbase-cli:f60ad7] server-add -c 172.23.108.103:8091 --server-add 172.23.97.238:8091 -u Administrator -p password --server-add-username Administrator --server-add-password password --services index
[2017-07-16T16:34:34-07:00, sequoiatools/couchbase-cli:e3a30b] rebalance -c 172.23.108.103:8091 -u Administrator -p password
[2017-07-16T16:34:57-07:00, sequoiatools/cmd:4052f2] 60
[2017-07-16T16:38:25-07:00, sequoiatools/couchbase-cli:ccb3de] server-add -c 172.23.108.103:8091 --server-add 172.23.97.239:8091 -u Administrator -p password --server-add-username Administrator --server-add-password password --services data Administrator -p password
```

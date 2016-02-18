[clusters]
systest =
    db1:8091,index,n1ql
    db2:8091,index,n1ql
    db3:8091,index,n1ql
    db4:8091,index,n1ql

[clients]
hosts =
   127.0.0.1
credentials = root:couchbase

[storage]
data = /data
index = /data

[credentials]
rest = Administrator:password
ssh = root:couchbase

[parameters]
Platform = Physical
OS = Centos 6.5 (Final)
CPU = Intel Xeon E5-2630 v2 (2.50GHz)(24 cores)(Data), Intel Xeon E5-2680 v3 (2.60GHz)(48 cores)(Query, Index)
Memory = 64GB (Data), 256GB (Index, Query)
Disk = SDD

package internal

import (
	"errors"
	"fmt"
	"github.com/couchbase/gocb/v2"
)

func CreateUtilities(cluster *gocb.Cluster, bucketName string, scopeName string, collectionName string, capella bool) {

	bucketMgr := cluster.Buckets()
	_ = bucketMgr.CreateBucket(gocb.CreateBucketSettings{
		BucketSettings: gocb.BucketSettings{
			Name:                 bucketName,
			FlushEnabled:         true,
			ReplicaIndexDisabled: true,
			RAMQuotaMB:           1024,
			NumReplicas:          0,
			BucketType:           gocb.CouchbaseBucketType,
		},
		ConflictResolutionType: gocb.ConflictResolutionTypeSequenceNumber,
	}, nil)

	bucket := cluster.Bucket(bucketName)

	collections := bucket.Collections()

	err := collections.CreateScope(scopeName, nil)
	if err != nil {
		if errors.Is(err, gocb.ErrScopeExists) {
			fmt.Println("Scope already exists")
		} else {
			panic(err)
		}
	}

	collection := gocb.CollectionSpec{
		Name:      collectionName,
		ScopeName: scopeName,
	}

	err = collections.CreateCollection(collection, nil)
	if err != nil {
		if errors.Is(err, gocb.ErrCollectionExists) {
			fmt.Printf("collection %s already exists\n", collection.Name)
		} else {
			panic(err)
		}
	}

}

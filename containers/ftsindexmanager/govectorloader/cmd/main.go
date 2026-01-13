package main

import (
	"encoding/base64"
	"flag"
	"fmt"
	"github.com/couchbase/gocb/v2"
	"log"
	"main/internal"
	"sync"
	"time"
)

func main() {

	var nodeAddress string
	var bucketName string
	var scopeName string
	var username string
	var password string
	var fieldName string
	var collectionName string
	var documentIdPrefix string
	var startIndex int
	var endIndex int
	var batchSize int
	var datasetName string
	var xattrFlag bool

	var percentagesToResize []float32
	var dimensionsForResize []int
	var percentagesToResizeStr string
	var dimensionsForResizeStr string
	var base64Flag bool
	var capella bool
	var provideDefaultDocs bool
	var invalidVecsLoader bool
	var invalidDimensions int
	var upsertFlag bool
	var deleteFlag bool
	var numQueries int
	var duration int
	var indexName string
	flag.StringVar(&nodeAddress, "nodeAddress", "", "IP address of the node")
	flag.StringVar(&bucketName, "bucketName", "default", "Bucket name")
	flag.StringVar(&scopeName, "scopeName", "_default", "Scope name")
	flag.StringVar(&collectionName, "collectionName", "_default", "Collection name")
	flag.StringVar(&username, "username", "", "username")
	flag.StringVar(&password, "password", "", "password")
	flag.StringVar(&fieldName, "fieldName", "vector_data", "fieldName")
	flag.StringVar(&documentIdPrefix, "documentIdPrefix", "", "documentIdPrefix")
	flag.IntVar(&startIndex, "startIndex", 0, "startIndex")
	flag.IntVar(&endIndex, "endIndex", 50, "endIndex")
	flag.IntVar(&batchSize, "batchSize", 600, "batchSize")
	flag.BoolVar(&provideDefaultDocs, "provideDefaultDocs", false, "provideDefaultDocs = true will upsert docs and then update docs for xattr (metadata)")
	flag.BoolVar(&capella, "capella", false, "pushing docs to capella?")
	flag.StringVar(&datasetName, "datasetName", "siftsmall", "Name of the dataset ('sift', 'siftsmall', 'gist')")
	flag.BoolVar(&xattrFlag, "xattrFlag", false, "xattrFlag = true will upsert vectors into xattr (metadata) and false will upsert vectors into document")
	flag.StringVar(&percentagesToResizeStr, "percentagesToResize", "", "Comma-separated list of float32 values")
	flag.StringVar(&dimensionsForResizeStr, "dimensionsForResize", "", "Comma-separated list of int values")
	flag.BoolVar(&base64Flag, "base64Flag", false, "true results in, embeddings get uploaded as base64 strings")
	flag.BoolVar(&invalidVecsLoader, "invalidVecsLoader", false, "s")
	flag.IntVar(&invalidDimensions, "invalidDimensions", 128, "s")
	flag.BoolVar(&upsertFlag, "upsertFlag", false, "")
	flag.BoolVar(&deleteFlag, "deleteFlag", false, "")
	flag.IntVar(&numQueries, "numQueries", 0, "flag to run queries")
	flag.IntVar(&duration, "duration", 1, "duration to run queries")
	flag.StringVar(&indexName, "indexName", "", "index name to run queires on")

	flag.Parse()
	var cluster *gocb.Cluster

	internal.Initialise_cluster(&cluster, capella, username, password, nodeAddress)

	// if !capella {
	// 	internal.CreateUtilities(cluster, bucketName, scopeName, collectionName, capella)
	// }

	bucket := cluster.Bucket(bucketName)

	err := bucket.WaitUntilReady(30*time.Second, nil)
	if err != nil {
		fmt.Printf("Error in waiting for bucket to be ready %v\n", err)
		return
	}

	scope := bucket.Scope(scopeName)
	collection := scope.Collection(collectionName)
	//dataset downloading and extraction
	baseUrl := "ftp://ftp.irisa.fr/local/texmex/corpus/"
	datasetUrl := baseUrl + datasetName + ".tar.gz"

	// Check if the dataset file already exists in the "raw/" folder
	if internal.DatasetExists("source/" + datasetName) {
		fmt.Println("Dataset file already exists. Skipping download.")
	} else {
		fmt.Println("Downloading the dataset")
		internal.DownloadDataset(datasetUrl, datasetName)
	}

	//Resize Vectors if required
	internal.DecriptResizeVariables(percentagesToResizeStr, dimensionsForResizeStr, &percentagesToResize, &dimensionsForResize)
	var datasetType = "base"
	if numQueries != 0 {
		datasetType = "query"
	}

	// Read dataset file and extract vector
	vectors, err := internal.ReadDataset(datasetName, datasetType)
	if err != nil {
		fmt.Printf("Error reading dataset %v\n", err)
		return
	}

	// Change vectors if required
	if percentagesToResizeStr != "" {
		err = internal.ResizeVectors(&vectors, percentagesToResize, dimensionsForResize)
		if err != nil {
			log.Printf("Error resizing vectors %v\n", err)
		}
	}

	//FOR RUNNING QUERIES
	if numQueries != 0 {
		internal.RunQueriesPerSecond(nodeAddress, indexName, vectors, username, password, numQueries, time.Duration(duration)*time.Minute, xattrFlag, base64Flag, capella)
		return
	}

	//FOR LOADING DATA
	if invalidVecsLoader {
		internal.InvalidVecsLoader(invalidDimensions, collection, xattrFlag, base64Flag)
	} else {
		var encodedVectors []string
		if base64Flag {
			for _, vector := range vectors {
				byteSlice := internal.FloatsToLittleEndianBytes(vector)
				base64String := base64.StdEncoding.EncodeToString(byteSlice)
				encodedVectors = append(encodedVectors, base64String)
			}
		}

		var wg sync.WaitGroup
		for startIndex != endIndex {
			end := startIndex + batchSize
			if end > endIndex {
				end = endIndex
			}
			wg.Add(end - startIndex)
			for j := startIndex; j < end; j++ {
				if xattrFlag {
					if base64Flag {
						vectArr := encodedVectors[j%len(encodedVectors)]
						go internal.UpsertXattrBase64(&wg, collection, fmt.Sprintf("%s%d", documentIdPrefix, j+1), vectArr, j+1, provideDefaultDocs)
					} else {
						vectArr := vectors[j%len(vectors)]
						go internal.UpsertXattr(&wg, collection, fmt.Sprintf("%s%d", documentIdPrefix, j+1), vectArr, j+1, provideDefaultDocs)
					}
				} else {
					if base64Flag {
						vectArr := encodedVectors[j%len(encodedVectors)]
						go internal.UpsertBase64(&wg, collection, fmt.Sprintf("%s%d", documentIdPrefix, j+1), vectArr, j+1, provideDefaultDocs)
					} else {
						vectArr := vectors[j%len(vectors)]
						go internal.UpsertVectors(&wg, collection, fmt.Sprintf("%s%d", documentIdPrefix, j+1), vectArr, j+1, provideDefaultDocs)
					}
				}

			}
			wg.Wait()
			startIndex = end
		}
	}
}

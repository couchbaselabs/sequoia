package main

import (
	"encoding/base64"
	"flag"
	"fmt"
	"github.com/couchbase/gocb/v2"
	"log"
	"main/internal"
	"math/rand"
	"strings"
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
	var embeddingFieldName string
	var collectionName string
	var documentIdPrefix string
	var startIndex int
	var endIndex int
	var batchSize int
	var datasetName string
	var xattrFlag bool
	var docSchema string
	var departmentsCount int
	var employeesPerDept int
	var projectsPerDept int
	var locationsCount int
	var seed int64

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
	flag.StringVar(&embeddingFieldName, "embeddingFieldName", "embedding", "Field name to use for embeddings in nested schemas")
	flag.StringVar(&documentIdPrefix, "documentIdPrefix", "", "documentIdPrefix")
	flag.IntVar(&startIndex, "startIndex", 0, "startIndex")
	flag.IntVar(&endIndex, "endIndex", 50, "endIndex")
	flag.IntVar(&batchSize, "batchSize", 600, "batchSize")
	flag.BoolVar(&provideDefaultDocs, "provideDefaultDocs", false, "provideDefaultDocs = true will upsert docs and then update docs for xattr (metadata)")
	flag.BoolVar(&capella, "capella", false, "pushing docs to capella?")
	flag.StringVar(&datasetName, "datasetName", "siftsmall", "Name of the dataset ('sift', 'siftsmall', 'gist')")
	flag.StringVar(&docSchema, "docSchema", "flat", "Document schema to write: flat (existing) | company (nested company schema)")
	flag.IntVar(&departmentsCount, "departmentsCount", 2, "Number of departments to create in company schema")
	flag.IntVar(&employeesPerDept, "employeesPerDept", 2, "Number of employees per department in company schema")
	flag.IntVar(&projectsPerDept, "projectsPerDept", 2, "Number of projects per department in company schema")
	flag.IntVar(&locationsCount, "locationsCount", 2, "Number of locations to create in company schema")
	flag.Int64Var(&seed, "seed", 0, "Random seed (0 means use current time)")
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
		var wg sync.WaitGroup
		docSchema = strings.ToLower(strings.TrimSpace(docSchema))
		// Backwards-compat: if docSchema isn't provided (or is empty/unknown), behave exactly like the legacy loader.
		if docSchema == "" {
			docSchema = "flat"
		}
		switch docSchema {
		case "company":
			if xattrFlag {
				log.Printf("docSchema=company currently supports only document fields (xattrFlag=false)")
				return
			}
			if len(vectors) == 0 {
				log.Printf("No vectors loaded; cannot build company docs")
				return
			}
			if seed == 0 {
				seed = time.Now().UnixNano()
			}
			rng := rand.New(rand.NewSource(seed))

			embedPerDoc, err := internal.CompanyEmbeddingsNeeded(departmentsCount, employeesPerDept, projectsPerDept, locationsCount)
			if err != nil {
				log.Printf("Invalid company schema params: %v", err)
				return
			}

			totalDocs := endIndex - startIndex
			if totalDocs <= 0 {
				log.Printf("Nothing to do: endIndex (%d) must be > startIndex (%d)", endIndex, startIndex)
				return
			}
			totalEmbeddingsNeeded := totalDocs * embedPerDoc

			// Build a shuffled pool of vector indices large enough for all docs.
			// This avoids a predictable repeating pattern; repeats happen only when totalEmbeddingsNeeded > len(vectors),
			// in which case we append another permutation, etc.
			vectorIdxPool := make([]int, 0, totalEmbeddingsNeeded)
			for len(vectorIdxPool) < totalEmbeddingsNeeded {
				vectorIdxPool = append(vectorIdxPool, rng.Perm(len(vectors))...)
			}

			originalStart := startIndex
			for startIndex != endIndex {
				end := startIndex + batchSize
				if end > endIndex {
					end = endIndex
				}
				wg.Add(end - startIndex)
				for j := startIndex; j < end; j++ {
					docID := fmt.Sprintf("%s%d", documentIdPrefix, j+1)
					docNum := j - originalStart
					offset := docNum * embedPerDoc
					vectorIdxs := vectorIdxPool[offset : offset+embedPerDoc]
					go internal.UpsertCompanyDoc(
						&wg,
						collection,
						docID,
						vectors,
						vectorIdxs,
						embeddingFieldName,
						base64Flag,
						departmentsCount,
						employeesPerDept,
						projectsPerDept,
						locationsCount,
					)
				}
				wg.Wait()
				startIndex = end
			}
		default:
			// Default path = legacy behavior (flat).
			var encodedVectors []string
			if base64Flag {
				for _, vector := range vectors {
					byteSlice := internal.FloatsToLittleEndianBytes(vector)
					base64String := base64.StdEncoding.EncodeToString(byteSlice)
					encodedVectors = append(encodedVectors, base64String)
				}
			}

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
}

package synloader

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"
	"sync"

	"github.com/couchbase/gocb/v2"
)

type ThesaurusEntry struct {
	Word     []string `json:"word"`
	Synonyms []string `json:"synonyms"`
}

type OutputFormat1 struct {
	Input    []string `json:"input"`
	Synonyms []string `json:"synonyms"`
}

type OutputFormat2 struct {
	Synonyms []string `json:"synonyms"`
}

func worker(id int, jobs <-chan ThesaurusEntry, cluster *gocb.Cluster, bucketName, scopeName, collectionName string, format int, wg *sync.WaitGroup) {
	defer wg.Done()
	bucket := cluster.Bucket(bucketName)
	collection := bucket.Scope(scopeName).Collection(collectionName)

	for entry := range jobs {
		docID := fmt.Sprintf("thesaurus_%s", entry.Word[0])

		var doc interface{}
		if format == 1 {
			doc = OutputFormat1{
				Input:    entry.Word,
				Synonyms: entry.Synonyms,
			}
		} else {
			entry.Synonyms = append(entry.Synonyms, entry.Word...)
			doc = OutputFormat2{Synonyms: entry.Synonyms}
		}

		_, err := collection.Upsert(docID, doc, nil)
		if err != nil {
			log.Printf("Worker %d: Failed to insert doc %s: %v", id, docID, err)
		}
	}
}

func SynLoader(bucket, scope, collection string, format, numWorkers int, cbURL, cbUser, cbPass string) (bool, error) {

	cbConnStr := "couchbase://" + cbURL
	flag.Parse()

	filePath := "data/data.json"

	cluster, err := gocb.Connect(cbConnStr, gocb.ClusterOptions{Authenticator: gocb.PasswordAuthenticator{
		Username: cbUser, Password: cbPass,
	}})
	if err != nil {
		// log.Fatalf("Failed to connect to Couchbase: %v", err)
		return false, err
	}

	data, err := os.ReadFile(filePath)
	if err != nil {
		// log.Fatalf("Failed to read file: %v", err)
		return false, err
	}

	var thesaurusData []ThesaurusEntry
	if err := json.Unmarshal(data, &thesaurusData); err != nil {
		// log.Fatalf("Error parsing JSON: %v", err)
		return false, err
	}

	jobs := make(chan ThesaurusEntry, 100)

	var wg sync.WaitGroup
	for i := 0; i < numWorkers; i++ {
		wg.Add(1)
		go worker(i, jobs, cluster, bucket, scope, collection, format, &wg)
	}

	for _, entry := range thesaurusData {
		jobs <- entry
	}

	close(jobs)
	wg.Wait()

	return true, nil
}

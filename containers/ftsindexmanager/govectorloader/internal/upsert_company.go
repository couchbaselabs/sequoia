package internal

import (
	"github.com/couchbase/gocb/v2"
	"log"
	"sync"
	"time"
)

// UpsertCompanyDoc creates/upserts a full nested company document with embeddings at every object.
// This is used by cmd/main.go when docSchema=company.
func UpsertCompanyDoc(
	waitGroup *sync.WaitGroup,
	collection *gocb.Collection,
	documentID string,
	vectors [][]float32,
	vectorIdxs []int,
	embeddingFieldName string,
	base64Flag bool,
	departmentsCount int,
	employeesPerDept int,
	projectsPerDept int,
	locationsCount int,
) {
	defer waitGroup.Done()

	doc, err := BuildCompanyDoc(
		documentID,
		vectors,
		vectorIdxs,
		embeddingFieldName,
		base64Flag,
		departmentsCount,
		employeesPerDept,
		projectsPerDept,
		locationsCount,
	)
	if err != nil {
		log.Printf("Error building company doc for %s: %v", documentID, err)
		return
	}

	// Upsert with retry (similar spirit to other helpers).
	for i := 0; i < 4; i++ {
		if i == 3 {
			log.Fatalf("Doc %s not upserted even after 3 retries. Exiting..", documentID)
		}
		_, upsertErr := collection.Upsert(documentID, doc, &gocb.UpsertOptions{
			Timeout: 10050 * time.Millisecond,
		})
		if upsertErr != nil {
			log.Print("Upsert operation failed. Retrying.\n")
			continue
		}
		break
	}
}

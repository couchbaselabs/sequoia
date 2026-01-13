package internal

import (
	"github.com/couchbase/gocb/v2"
	"github.com/go-faker/faker/v4"
	"log"
	"sync"
	"time"
)

func UpsertXattr(waitGroup *sync.WaitGroup, collection *gocb.Collection, documentID string, vectorData []float32, ind int, provideDefaultDocs bool) {
	defer waitGroup.Done()

	type Data struct {
		Sno   int    `json:"sno"`
		Sname string `json:"sname"`
		Id    string `json:"id"`
	}
	counter := 0
	if provideDefaultDocs {
		for i := 0; i < 3; i++ {
			var _, err = collection.Upsert(documentID,
				Data{
					Sno:   ind,
					Sname: faker.Name(),
					Id:    documentID,
				}, nil)
			if err != nil {
				log.Print("Default Doc creation error. Retrying.\n")
				counter++
			} else {
				break
			}
		}
	}

	if counter != 3 {
		counter = 0
		for i := 0; i < 4; i++ {
			if i == 3 {
				panic("Doc not upserted even after 3 retries. Exiting..")
			}

			mops := []gocb.MutateInSpec{
				gocb.UpsertSpec("vector_data", vectorData, &gocb.UpsertSpecOptions{
					CreatePath: true,
					IsXattr:    true,
				}),
			}
			_, err := collection.MutateIn(documentID, mops, &gocb.MutateInOptions{
				Timeout: 10050 * time.Millisecond,
			})
			if err != nil {
				log.Print("Upsert operation failed. Retrying.\n")
				counter++
			} else {
				// log.Printf("Document ID %v upsert successful. Xattr - True, Base64 - False\n", documentID)
				break
			}
		}
	} else {
		panic("Doc not upserted even after 3 retries. Exiting..")
	}
}

func UpsertVectors(waitGroup *sync.WaitGroup, collection *gocb.Collection, documentID string, vectorData []float32, ind int, provideDefaultDocs bool) {
	defer waitGroup.Done()

	type Data struct {
		Sno    int       `json:"sno"`
		Sname  string    `json:"sname"`
		Id     string    `json:"id"`
		Vector []float32 `json:"vector_data"`
	}
	counter := 0
	if provideDefaultDocs {
		for i := 0; i < 3; i++ {
			var _, err = collection.Upsert(documentID,
				Data{
					Sno:    ind,
					Sname:  faker.Name(),
					Id:     documentID,
					Vector: vectorData,
				}, nil)
			if err != nil {
				log.Print("Default Doc creation error. Retrying.\n")
				counter++
			} else {
				// fmt.Printf("Document ID %v upsert successful. Xattr - False, Base64 - False\n", documentID)
				break
			}
		}
	} else {
		if counter != 3 {
			counter = 0
			for i := 0; i < 4; i++ {
				if i == 3 {
					panic("Doc not upserted even after 3 retries. Exiting..")
				}

				mops := []gocb.MutateInSpec{
					gocb.UpsertSpec("vector_data", vectorData, &gocb.UpsertSpecOptions{}),
				}
				_, err := collection.MutateIn(documentID, mops, &gocb.MutateInOptions{
					Timeout: 10050 * time.Millisecond,
				})
				if err != nil {
					log.Print("Upsert operation failed. Retrying.\n")
					counter++
				} else {
					// log.Printf("Document ID %v upsert successful. Xattr - False, Base64 - False\n", documentID)
					break
				}
			}
		} else {
			log.Fatalf("Doc not upserted even after 3 retries. Exiting..")
		}
	}

}

func UpsertXattrBase64(waitGroup *sync.WaitGroup, collection *gocb.Collection, documentID string, vectorData string, ind int, provideDefaultDocs bool) {
	defer waitGroup.Done()

	type Data struct {
		Sno   int    `json:"sno"`
		Sname string `json:"sname"`
		Id    string `json:"id"`
	}
	counter := 0
	if provideDefaultDocs {
		for i := 0; i < 3; i++ {
			var _, err = collection.Upsert(documentID,
				Data{
					Sno:   ind,
					Sname: faker.Name(),
					Id:    documentID,
				}, nil)
			if err != nil {
				log.Print("Default Doc creation error. Retrying.\n")
				counter++
			} else {
				break
			}
		}
	}

	if counter != 3 {
		counter = 0
		for i := 0; i < 4; i++ {
			if i == 3 {
				panic("Doc not upserted even after 3 retries. Exiting..")
			}

			mops := []gocb.MutateInSpec{
				gocb.UpsertSpec("vector_encoded", vectorData, &gocb.UpsertSpecOptions{
					CreatePath: true,
					IsXattr:    true,
				}),
			}
			_, err := collection.MutateIn(documentID, mops, &gocb.MutateInOptions{
				Timeout: 10050 * time.Millisecond,
			})
			if err != nil {
				log.Print("Upsert operation failed. Retrying.\n")
				counter++
			} else {
				// log.Printf("Document ID %v upsert successful. Xattr - True, Base64 - True\n", documentID)
				break
			}
		}
	} else {
		log.Fatalf("Doc not upserted even after 3 retries. Exiting..")
	}
}

func UpsertBase64(waitGroup *sync.WaitGroup, collection *gocb.Collection, documentID string, vectorData string, ind int, provideDefaultDocs bool) {
	defer waitGroup.Done()

	type Data struct {
		Sno   int    `json:"sno"`
		Sname string `json:"sname"`
		Id    string `json:"id"`
	}
	counter := 0
	if provideDefaultDocs {
		for i := 0; i < 3; i++ {

			var _, err = collection.Upsert(documentID,
				Data{
					Sno:   ind,
					Sname: faker.Name(),
					Id:    documentID,
				}, nil)
			if err != nil {
				log.Print("Default Doc creation error. Retrying.\n")
				counter++
			} else {
				break
			}
		}
	}

	if counter != 3 {
		counter = 0
		for i := 0; i < 4; i++ {
			if i == 3 {
				panic("Doc not upserted even after 3 retries. Exiting..")
			}

			mops := []gocb.MutateInSpec{
				gocb.UpsertSpec("vector_data_base64", vectorData, &gocb.UpsertSpecOptions{}),
			}
			_, err := collection.MutateIn(documentID, mops, &gocb.MutateInOptions{
				Timeout: 10050 * time.Millisecond,
			})
			if err != nil {
				log.Print("Upsert operation failed. Retrying.\n")
				counter++
			} else {
				// log.Printf("Document ID %v upsert successful. Xattr - False, Base64 - True\n", documentID)
				break
			}
		}
	} else {
		log.Fatalf("Doc not upserted even after 3 retries. Exiting..")
	}
}

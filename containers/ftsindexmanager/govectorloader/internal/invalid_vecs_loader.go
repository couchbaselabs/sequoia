package internal 

import (
	"fmt"
	"github.com/couchbase/gocb/v2"
	"github.com/go-faker/faker/v4"
	"log"
)

func InvalidVecsLoader(invalidDimensions int, collection *gocb.Collection, xattrFlag bool, base64Flag bool) {

	k := invalidDimensions

	item1 := []interface{}{"A"}
	for i := 1; i < k; i++ {
		item1 = append(item1, i)
	}

	item2 := []interface{}{"2.0"}
	for i := 1; i < k; i++ {
		item2 = append(item2, i)
	}

	item3 := []interface{}{"/"}
	for i := 1; i < k; i++ {
		item3 = append(item3, i)
	}

	item4 := []interface{}{}
	for i := 1; i < k-1; i++ {
		item4 = append(item4, i)
	}

	item5 := "Q291Y2hiYXNlIGlzIGdyZWF0ICB3c2txY21lcW9qZmNlcXcgZGZlIGpkbmZldyBmamUgd2Zob3VyIGwgZnJ3OWZmIGdmaXJ3ZnJ3IGhmaXJoIGZlcmYgcmYgZXJpamZoZXJ1OWdlcmcgb2ogZmhlcm9hZiBmZTlmdSBnZXJnIHJlOWd1cmZyZWZlcmcgaHJlIG8gZXJmZ2Vyb2ZyZmdvdQ"

	incorrect_vecs := [][]interface{}{item1, item2, item3, item4}
	incorrect_vecs = append(incorrect_vecs, []interface{}{item5})

	for _, item := range incorrect_vecs {
		fmt.Println(item)
	}
	if xattrFlag {
		if base64Flag {
			type Data struct {
				Sno   int    `json:"sno"`
				Sname string `json:"sname"`
				Id    string `json:"id"`
			}

			documentID := fmt.Sprintf("%s%d", "incorrect", 0)
			for j:=0;j<3;j++ {
				var _, err = collection.Upsert(documentID,
				Data{
					Sno:   0,
					Sname: faker.Name(),
					Id:    documentID,
				}, nil)
				if err != nil {
					log.Fatalf("Unable to upsert doc %v", err)
					return
				} else {
					break
				}
			}
			for j:=0;j<3;j++ {
				var _, errr = collection.MutateIn(documentID, []gocb.MutateInSpec{
					gocb.UpsertSpec("vector_encoded", item5, &gocb.UpsertSpecOptions{
						CreatePath: true,
						IsXattr:    true,
					}),
				},
					nil,
				)
				if errr != nil {
					fmt.Printf("Error mutating document %v : %v Retrying\n", documentID, errr)
				} else {
					fmt.Printf("Document ID %v got updated with vector data in xattrs\n", documentID)
				}
			}
		} else {
			type Data struct {
				Sno   int    `json:"sno"`
				Sname string `json:"sname"`
				Id    string `json:"id"`
			}
			
			for i := 0; i < 4; i++ {

			documentID := fmt.Sprintf("%s%d", "incorrect", i)
			for j:=0;j<3;j++ {
				var _, err = collection.Upsert(documentID,
				Data{
					Sno:   0,
					Sname: faker.Name(),
					Id:    documentID,
				}, nil)
				if err != nil {
					log.Fatalf("Unable to upsert doc %v", err)
					return
				} else {
					break
				}
				}

			}
			for i := 0; i < 4; i++ {
			documentID := fmt.Sprintf("%s%d", "incorrect", i)
			for j:=0;j<3;j++ {
				var _, errr = collection.MutateIn(documentID, []gocb.MutateInSpec{
					gocb.UpsertSpec("vector_data", incorrect_vecs[i], &gocb.UpsertSpecOptions{
						CreatePath: true,
						IsXattr:    true,
					}),
				},
					nil,
				)
				if errr != nil {
					fmt.Printf("Error mutating document %v : %v Retrying\n", documentID, errr)
				} else {
					fmt.Printf("Document ID %v got updated with vector data in xattrs\n", documentID)
				}
			}
		}			
	}
	} else {

		if base64Flag {
			type Data struct {
				Sno    int       `json:"sno"`
				Sname  string    `json:"sname"`
				Id     string    `json:"id"`
				Vector string `json:"vector_data_base64"`
			}
			documentID := fmt.Sprintf("%s%d", "incorrect", 0)
			for j := 0; j < 3; j++ {
				var _, err = collection.Upsert(documentID,
					Data{
						Sno:    0,
						Sname:  faker.Name(),
						Id:     documentID,
						Vector: item5,
					}, nil)
				if err != nil {
					log.Fatal(err)
				} else {
					fmt.Printf("Document ID %v got upserted with vector in doc.\n", documentID)
					break
				}
		
			}
		} else {
			type Data struct {
				Sno    int       `json:"sno"`
				Sname  string    `json:"sname"`
				Id     string    `json:"id"`
				Vector []interface{} `json:"vector_data"`
			}
			for i := 0; i < 4; i++ {
				documentID := fmt.Sprintf("%s%d", "incorrect", i)

				for j := 0; j < 3; j++ {
					var _, err = collection.Upsert(documentID,
						Data{
							Sno:    i,
							Sname:  faker.Name(),
							Id:     documentID,
							Vector: incorrect_vecs[i],
						}, nil)
					if err != nil {
						log.Fatal(err)
					} else {
						fmt.Printf("Document ID %v got upserted with vector in doc.\n", documentID)
						break
					}
				}
			}	
	}
	}
}

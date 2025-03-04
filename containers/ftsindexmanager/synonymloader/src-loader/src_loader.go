package srcloader

import (
	"encoding/json"
	"fmt"
	"log"
	"math/rand"
	"os"
	"sort"
	"strings"
	"sync"
	"github.com/couchbase/gocb/v2"
)

const loremIpsum = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua."

type ThesaurusEntry struct {
	Word     []string `json:"word"`
	Synonyms []string `json:"synonyms"`
}

type ResponseObj struct {
	WordDocMap       map[string][]string `json:"word_doc_map"`
	FinalWordDocMap  map[string][]string `json:"final_word_doc_map"`
}


func worker(id int, jobs <-chan string, cluster *gocb.Cluster, bucketName, scopeName, collectionName string, text string, wordList []string, wg *sync.WaitGroup, wordDocMap map[string][]string, mapMutex *sync.Mutex) {
	defer wg.Done()
	bucket := cluster.Bucket(bucketName)
	collection := bucket.Scope(scopeName).Collection(collectionName)

	for docID := range jobs {
		selectedWords := selectRandomWords(5, wordList)

		modifiedText := insertWordsIntoText(text, selectedWords)

		doc := map[string]string{
			"text": modifiedText,
		}

		_, err := collection.Upsert(docID, doc, nil)
		if err != nil {
			log.Printf("Worker %d: Failed to insert doc %s: %v", id, docID, err)
		}

		mapMutex.Lock()
		for word := range selectedWords {
			wordDocMap[word] = append(wordDocMap[word], docID)
		}
		mapMutex.Unlock()
	}
}

func SrcLoader(bucket, scope, collection string, numWorkers int, cbURL, cbUser, cbPass string, numDocs int) (ResponseObj, error){

	filepath := "data/data.json"
	cluster, err := gocb.Connect("couchbase://"+cbURL, gocb.ClusterOptions{
		Authenticator: gocb.PasswordAuthenticator{
			Username: cbUser, Password: cbPass,
		},
	})
	if err != nil {
		log.Fatalf("Failed to connect to Couchbase: %v", err)
	}


	data, err := os.ReadFile(filepath)
	if err != nil {
		log.Fatalf("Failed to read file: %v", err)
	}

	var thesaurusData []ThesaurusEntry
	if err := json.Unmarshal(data, &thesaurusData); err != nil {
		log.Fatalf("Error parsing JSON: %v", err)
	}


	wordSet := make(map[string]struct{})
	for _, entry := range thesaurusData {
		for _, word := range entry.Word {
			loweredWord := strings.ToLower(word)
			wordSet[loweredWord] = struct{}{}
		}
		// loweredWord := strings.ToLower(entry.Word)
		// wordSet[loweredWord] = struct{}{}
		for _, syn := range entry.Synonyms {
			loweredSyn := strings.ToLower(syn)
			wordSet[loweredSyn] = struct{}{}
		}
	}

	wordList := make([]string, 0, len(wordSet))
	for word := range wordSet {
		wordList = append(wordList, word)
	}

	jobs := make(chan string, 100)
	var wg sync.WaitGroup
	wordDocMap := make(map[string][]string)
	var mapMutex sync.Mutex

	for i := 0; i < numWorkers; i++ {
		wg.Add(1)
		go worker(i, jobs, cluster, bucket, scope, collection, loremIpsum, wordList, &wg, wordDocMap, &mapMutex)
	}

	for i := 1; i <= numDocs; i++ {
		docID := fmt.Sprintf("doc%d", i)
		jobs <- docID
	}

	close(jobs)
	wg.Wait()

	wordDocJSON, _ := json.MarshalIndent(wordDocMap, "", "	")
	
	temp := make(map[string][]string)
	json.Unmarshal(wordDocJSON, &temp)

	finalWordDocMap := mergeWordMappings(thesaurusData, wordDocMap)

	finalWordDocJSON, _ := json.MarshalIndent(finalWordDocMap, "", "	")
	temp1 := make(map[string][]string)
	json.Unmarshal(finalWordDocJSON, &temp1)

	response := ResponseObj{
		WordDocMap:       temp,
		FinalWordDocMap : temp1,
	}

	json.NewEncoder(os.Stdout).Encode(response)
	return response, nil
	
}

func selectRandomWords(k int, wordList []string) map[string]struct{} {
	selectedWords := make(map[string]struct{})
	if len(wordList) == 0 {
		return selectedWords
	}

	for len(selectedWords) < k {
		randWord := wordList[rand.Intn(len(wordList))]
		selectedWords[randWord] = struct{}{}
	}
	return selectedWords
}


func insertWordsIntoText(text string, words map[string]struct{}) string {
	wordsSlice := make([]string, 0, len(words))
	for word := range words {
		wordsSlice = append(wordsSlice, word)
	}

	wordsArray := strings.Fields(text)
	insertPositions := rand.Perm(len(wordsArray))[:len(wordsSlice)]

	for i, pos := range insertPositions {
		wordsArray[pos] = wordsSlice[i] + " " + wordsArray[pos]
	}

	return strings.Join(wordsArray, " ")
}


func mergeWordMappings(thesaurusData []ThesaurusEntry, wordDocMap map[string][]string) map[string][]string {
	finalWordDocMap := make(map[string][]string)

	for _, entry := range thesaurusData {
		wordSet := make(map[string]struct{})
		for _, word := range entry.Word {
			wordSet[strings.ToLower(word)] = struct{}{}
		}

		for _, synonym := range entry.Synonyms {
			wordSet[strings.ToLower(synonym)] = struct{}{}
		}

		mergedDocList := make(map[string]struct{})
		for word := range wordSet {
			if docs, exists := wordDocMap[word]; exists {
				for _, docID := range docs {
					mergedDocList[docID] = struct{}{}
				}
			}
		}

		finalDocList := make([]string, 0, len(mergedDocList))
		for docID := range mergedDocList {
			finalDocList = append(finalDocList, docID)
		}
		sort.Strings(finalDocList)
		for _, word := range entry.Word {
			finalWordDocMap[strings.ToLower(word)] = finalDocList
		}
	}
	return finalWordDocMap
}
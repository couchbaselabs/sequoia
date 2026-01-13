package internal

import (
	"fmt"
	"math/rand"
	"strings"
	"sync"
	"time"
)

var Passcount int
var Failcount int
var Totalcount int

func callAPI(username string, password string, url string, payload map[string]interface{}) (map[string]interface{}, error) {
	//fmt.Printf("Executing query on url %s with payload %v", url, payload)
	apiClient := NewAPIClient(url)
	resp, err := apiClient.DoRequest("POST", username, password, payload)
	if err != nil {
		return nil, err
	}
	postResult, err := ProcessResponse(resp)
	if err != nil {
		return nil, err
	}
	return postResult, nil
}

func getSearchNodes(nodeAddress string) []string {
	var surls []string
	urls := resolve(nodeAddress)
	for _, x := range urls {
		services := strings.Split(x, "-")[1]
		if strings.Contains(services, "s") {
			surls = append(surls, x)
		}
	}
	return surls
}

func resolveAndGetSearchNode(nodeAddress string, capella bool) string {
	var url string
	if capella {
		urls := getSearchNodes(nodeAddress)
		url = fmt.Sprintf("https://%s:18094/", urls[0])
	} else {
		url = fmt.Sprintf("http://%s:8094/", nodeAddress)
	}
	return url
}

func SimulateQuery(nodeAddress string, indexName string, vector []float32, username string, password string, xattr bool, base64 bool, capella bool) {
	var url string
	if capella {
		urls := getSearchNodes(nodeAddress)
		url = fmt.Sprintf("https://%s:18094/api/index/%s/query", urls[rand.Intn(len(urls))], indexName)
	} else {
		//nodes := []string{"172.23.105.122", "172.23.106.171", "172.23.106.30", "172.23.97.108", "172.23.97.109"}
		//url = fmt.Sprintf("http://%s:8094/api/index/%s/query", nodes[rand.Intn(len(nodes))], indexName)
		url = fmt.Sprintf("http://%s:8094/api/index/%s/query", nodeAddress, indexName)
	}
	var field = "vector_data"
	if xattr {
		field = "_$xattrs.vector_data"
	}
	if base64 {
		field = "vector_data_base64"
	}

	payload := map[string]interface{}{
		"query": map[string]interface{}{
			"match_none": struct{}{},
		},
		"explain": true,
		"fields":  []string{"*"},
		"knn": []map[string]interface{}{
			{
				"field":  field,
				"k":      10,
				"vector": vector,
			},
		},
	}

	result, err := callAPI(username, password, url, payload)
	Totalcount++
	if err != nil {
		fmt.Printf("Error running query %v\n", err)
	}
	if result["status"] == "fail" {
		fmt.Println(result)
		Failcount++
	} else {
		Passcount++
		fmt.Println(result["status"], "Total Hits:", result["total_hits"])
	}

}

func getAllIndexes(nodeAddress string, username string, password string, capella bool) (map[string]interface{}, error) {
	url := resolveAndGetSearchNode(nodeAddress, capella)
	url = url + "api/index"
	apiClient := NewAPIClient(url)
	resp, err := apiClient.DoRequest("GET", username, password, nil)
	if err != nil {
		return nil, err
	}
	postResult, err := ProcessResponse(resp)
	if err != nil {
		return nil, err
	}
	return postResult, nil
}

func getIndexNames(nodeAddress string, username string, password string, indexNames *[]string, capella bool) {
	indexes, err := getAllIndexes(nodeAddress, username, password, capella)
	if err != nil {
		fmt.Printf("Error retriving index names := %v :=Indexes %v", err, indexes)
		return
	}
	indexDefs, _ := indexes["indexDefs"].(map[string]interface{})
	indexDefs2, _ := indexDefs["indexDefs"].(map[string]interface{})
	for index := range indexDefs2 {
		*indexNames = append(*indexNames, index)
	}
}

func run(nodeAddress string, indexName string, vector [][]float32, username string, password string, n int, duration time.Duration, xattr bool, base64 bool, wg *sync.WaitGroup, capella bool) {
	defer wg.Done()
	startTime := time.Now()
	for time.Since(startTime) < duration {
		timeB4 := time.Now()
		for i := 0; i < n; i++ {
			go SimulateQuery(nodeAddress, indexName, vector[rand.Intn(len(vector)-1)], username, password, xattr, base64, capella)
		}
		timeToSleep := time.Second - time.Since(timeB4)
		if timeToSleep > 0 {
			time.Sleep(timeToSleep)
		}
	}
}
func RunQueriesPerSecond(nodeAddress string, indexName string, vector [][]float32, username string, password string, n int, duration time.Duration, xattr bool, base64 bool, capella bool) {
	var indexNames []string
	var customizeXattrandBase64params bool
	if indexName != "" {
		customizeXattrandBase64params = true
		indexNames = append(indexNames, indexName)
	} else {
		getIndexNames(nodeAddress, username, password, &indexNames, capella)
	}
	var wg sync.WaitGroup
	for _, index := range indexNames {
		wg.Add(1)
		if customizeXattrandBase64params {
			if strings.Contains(index, "xattr") {
				go run(nodeAddress, index, vector, username, password, n, duration, true, base64, &wg, capella)
			} else if strings.Contains(index, "base") {
				go run(nodeAddress, index, vector, username, password, n, duration, xattr, true, &wg, capella)
			} else {
				go run(nodeAddress, index, vector, username, password, n, duration, xattr, base64, &wg, capella)
			}
		} else {
			go run(nodeAddress, index, vector, username, password, n, duration, xattr, base64, &wg, capella)
		}

	}
	wg.Wait()
	fmt.Println(fmt.Sprintf("Totalcount %d Passcount %d Failcount %d", Totalcount, Passcount, Failcount))

}

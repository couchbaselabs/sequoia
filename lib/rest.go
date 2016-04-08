package sequoia

import (
	"encoding/json"
	"fmt"
	"io/ioutil"
	"net/http"
	"time"
)

type NodeSelf struct {
	MemoryTotal       int
	MemoryFree        int
	McdMemoryReserved int
	FtsMemoryQuota    int
	IndexMemoryQuota  int
	MemoryQuota       int
}

func GetMemTotal(host, user, password string) int {
	var n NodeSelf

	jsonRequest(host, user, password, &n)
	q := n.MemoryTotal
	if q == 0 {
		time.Sleep(5 * time.Second)
		return GetMemTotal(host, user, password)
	}
	q = q / 1048576 // mb
	return q
}

func GetMemReserved(host, user, password string) int {
	var n NodeSelf

	jsonRequest(host, user, password, &n)
	q := n.McdMemoryReserved
	if q == 0 {
		time.Sleep(5 * time.Second)
		return GetMemReserved(host, user, password)
	}
	return q
}

func jsonRequest(host, user, password string, v interface{}) {
	urlStr := fmt.Sprintf("http://%s/nodes/self", host)
	req, err := http.NewRequest("GET", urlStr, nil)
	chkerr(err)
	req.SetBasicAuth(user, password)

	client := &http.Client{}
	res, err := client.Do(req)
	chkerr(err)
	body, err := ioutil.ReadAll(res.Body)
	chkerr(err)
	err = json.Unmarshal(body, v)
	chkerr(err)
}

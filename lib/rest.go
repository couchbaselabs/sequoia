package sequoia

import (
	"encoding/json"
	"fmt"
	"io/ioutil"
	"net/http"
)

type NodeSelf struct {
	MemoryTotal       int
	MemoryFree        int
	McdMemoryReserved int
	FtsMemoryQuota    int
	IndexMemoryQuota  int
	MemoryQuota       int
}

func GetMemQuota(host, user, password string) int {
	n := new(NodeSelf)
	jsonRequest(host, user, password, &n)
	return n.MemoryQuota
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

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
	Services          []string
	Version           string
}

type NodeStatuses struct {
	Statuses map[string]NodeStatus
}

type NodeStatus struct {
	Status      map[string]string
	Healthy     map[string]string
	OtpNode     map[string]string
	Replication map[string]int
	Dataless    map[string]bool
}

func GetMemTotal(host, user, password string) int {
	var n NodeSelf

	err := getNodeSelf(host, user, password, &n)
	chkerr(err)

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

	err := getNodeSelf(host, user, password, &n)
	chkerr(err)

	q := n.McdMemoryReserved
	if q == 0 {
		time.Sleep(5 * time.Second)
		return GetMemReserved(host, user, password)
	}
	return q
}

func GetIndexQuota(host, user, password string) int {
	var n NodeSelf

	err := getNodeSelf(host, user, password, &n)
	chkerr(err)

	q := n.IndexMemoryQuota
	if q == 0 {
		time.Sleep(5 * time.Second)
		return GetIndexQuota(host, user, password)
	}
	return q
}

func NodeHasService(service, host, user, password string) bool {
	var n NodeSelf
	err := getNodeSelf(host, user, password, &n)
	if err != nil {
		return false
	}
	for _, s := range n.Services {
		if s == service {
			return true
		}
	}

	return false
}

func GetServerVersion(host, user, password string) string {
	var n NodeSelf

	err := getNodeSelf(host, user, password, &n)
	chkerr(err)

	q := n.Version
	if q == "" {
		time.Sleep(1 * time.Second)
		return GetServerVersion(host, user, password)
	}

	return q
}

func NodeIsSingle(host, user, password string) bool {

	var n interface{}
	var single bool = false
	if err := getNodeStatus(host, user, password, &n); err == nil {
		s := n.(map[string]interface{})
		single = len(s) == 1
	}
	return single
}

func getNodeStatus(host, user, password string, v interface{}) error {
	return _jsonRequest("http://%s/nodeStatuses", host, user, password, v)
}

func getNodeSelf(host, user, password string, v interface{}) error {
	return _jsonRequest("http://%s/nodes/self", host, user, password, v)
}

func _jsonRequest(url, host, user, password string, v interface{}) error {

	// setup request url
	urlStr := fmt.Sprintf(url, host)
	req, err := http.NewRequest("GET", urlStr, nil)
	chkerr(err)
	req.SetBasicAuth(user, password)

	// send client request
	client := &http.Client{}
	res, err := client.Do(req)
	if err != nil {
		return err
	}

	// unmarshal data to provided interface
	body, err := ioutil.ReadAll(res.Body)
	chkerr(err)
	err = json.Unmarshal(body, v)
	chkerr(err)
	return nil
}

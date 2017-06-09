package sequoia

import (
	"fmt"
	"time"
)

type RestClient struct {
	Clusters []ServerSpec
	Provider Provider
	Cm       *ContainerManager
}

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

type NodeStatuses map[string]NodeStatus

type NodeStatus struct {
	Status      string
	OtpNode     string
	Replication float64
	Dataless    bool
}

func (r *RestClient) GetServerVersion() string {
	host := r.GetOrchestrator()
	n := r.GetHostNodeSelf(host)
	return n.Version
}

func (r *RestClient) GetMemTotal(host string) int {
	n := r.GetHostNodeSelf(host)
	q := n.MemoryTotal
	if q == 0 {
		time.Sleep(5 * time.Second)
		return r.GetMemTotal(host)
	}
	q = q / 1048576 // mb
	return q
}

func (r *RestClient) GetMemReserved(host string) int {
	n := r.GetHostNodeSelf(host)
	q := n.McdMemoryReserved
	if q == 0 {
		time.Sleep(5 * time.Second)
		return r.GetMemReserved(host)
	}

	return q
}

func (r *RestClient) GetIndexQuota(host string) int {
	n := r.GetHostNodeSelf(host)
	q := n.IndexMemoryQuota
	if q == 0 {
		time.Sleep(5 * time.Second)
		return r.GetIndexQuota(host)
	}

	return q
}

func (r *RestClient) NodeHasService(service, host string) bool {
	n := r.GetHostNodeSelf(host)
	for _, s := range n.Services {
		if s == service {
			return true
		}
	}
	return false
}

func (r *RestClient) NodeIsSingle(host string) bool {

	n := r.GetHostNodeStatuses(host)
	single := len(n) == 1
	return single
}

func (r *RestClient) GetOrchestrator() string {
	cluster := r.Clusters[0]
	return cluster.Names[0]
}

func (r *RestClient) GetAuth(host string) string {
	for _, cluster := range r.Clusters {
		for _, _host := range cluster.Names {
			if _host == host {
				user := cluster.RestUsername
				pass := cluster.RestPassword
				return fmt.Sprintf("%s:%s", user, pass)
			}
		}
	}
	return ""
}

func (r *RestClient) GetHostNodeSelf(host string) NodeSelf {
	url := r.Provider.GetRestUrl(host)
	auth := r.GetAuth(host)
	n := r.GetNodeSelf(auth, url)
	return n
}

func (r *RestClient) GetHostNodeStatuses(host string) NodeStatuses {
	url := r.Provider.GetRestUrl(host)
	auth := r.GetAuth(host)
	n := r.GetNodeStatuses(auth, url)
	return n
}

func (r *RestClient) GetNodeSelf(auth, url string) NodeSelf {
	reqUrl := fmt.Sprintf("%s/nodes/self", url)
	var n NodeSelf
	r.JsonRequest(auth, reqUrl, &n)
	return n
}

func (r *RestClient) GetNodeStatuses(auth, url string) NodeStatuses {
	reqUrl := fmt.Sprintf("%s/nodeStatuses", url)
	var n NodeStatuses
	r.JsonRequest(auth, reqUrl, &n)
	return n
}

func (r *RestClient) JsonRequest(auth, restUrl string, v interface{}) {

	// run curl container to make rest request
	cmd := []string{"-u", auth, "-s", restUrl}
	id := r.Cm.RunRestContainer(cmd)

	// convert logs to json
	resp := r.Cm.GetLogs(id, "all")
	StringToJson(resp, &v)
}

package sequoia

import (
	"fmt"
	"github.com/streamrail/concurrent-map"
	"time"
)

type RestClient struct {
	Clusters        []ServerSpec
	Provider        Provider
	Cm              *ContainerManager
	TopologyChanged bool
	nodeSelfCache   cmap.ConcurrentMap
	nodeStatusCache cmap.ConcurrentMap
	IsWatching      bool
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

type RebalanceStatus struct {
	Status string
}

func NewRestClient(clusters []ServerSpec, provider Provider, cm *ContainerManager) RestClient {
	rest := RestClient{
		Clusters:        clusters,
		Provider:        provider,
		Cm:              cm,
		TopologyChanged: true,
		IsWatching:      false,
	}

	rest.resetCache()
	return rest
}

func (r *RestClient) resetCache() {
	r.nodeSelfCache = cmap.New()
	r.nodeStatusCache = cmap.New()
}

func (r *RestClient) WatchForTopologyChanges() {
	r.IsWatching = true
	ch := make(chan bool, 10)

	for {

		// wait before next check
		time.Sleep(20 * time.Second)

		for _, cluster := range r.Clusters {

			orchestrator := cluster.Names[0]
			if r.ClusterIsRebalancing(orchestrator) {
				r.resetCache()
				r.TopologyChanged = true
				// we're rebalancing, relax
				time.Sleep(60 * time.Second)
			}
			if r.TopologyChanged == false {
				// nodes cached and no topology changes have occured
				continue
			}
			for _, host := range cluster.Names {
				go func(h string) {
					ch <- true
					nodeSelf := r.getHostNodeSelf(h)
					r.nodeSelfCache.Set(h, nodeSelf)
					nodeStatus := r.getHostNodeStatuses(h)
					r.nodeStatusCache.Set(h, nodeStatus)
					<-ch
				}(host)
			}

		}
		r.TopologyChanged = false
	}

	r.IsWatching = false
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

func (r *RestClient) ClusterIsRebalancing(host string) bool {
	url := r.Provider.GetRestUrl(host)
	auth := r.GetAuth(host)
	s := r.GetRebalanceStatuses(auth, url)
	return s.Status != "none"
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

	if val, ok := r.nodeSelfCache.Get(host); ok {
		return val.(NodeSelf)
	}
	return r.getHostNodeSelf(host)
}

func (r *RestClient) getHostNodeSelf(host string) NodeSelf {

	url := r.Provider.GetRestUrl(host)
	auth := r.GetAuth(host)
	n := r.GetNodeSelf(auth, url)
	return n
}

func (r *RestClient) GetHostNodeStatuses(host string) NodeStatuses {

	if val, ok := r.nodeStatusCache.Get(host); ok {
		return val.(NodeStatuses)
	}
	return r.getHostNodeStatuses(host)
}

func (r *RestClient) getHostNodeStatuses(host string) NodeStatuses {
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

func (r *RestClient) GetRebalanceStatuses(auth, url string) RebalanceStatus {
	reqUrl := fmt.Sprintf("%s/pools/default/rebalanceProgress", url)
	var s RebalanceStatus
	r.JsonRequest(auth, reqUrl, &s)
	return s
}

//
func (r *RestClient) JsonRequest(auth, restUrl string, v interface{}) {
	// run curl container to make rest request
	cmd := []string{"-u", auth, "-s", restUrl}
	id, svcId := r.Cm.RunRestContainer(cmd)

	// convert logs to json
	resp := r.Cm.GetLogs(id, "all")
	StringToJson(resp, &v)

	// remove container
	if r.Cm.ProviderType == "swarm" {
		err := r.Cm.RemoveService(svcId)
		logerr(err)
	} else {
		err := r.Cm.RemoveContainer(id)
		logerr(err)
	}
}

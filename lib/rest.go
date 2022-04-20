package sequoia

import (
	"fmt"
	"time"

	cmap "github.com/streamrail/concurrent-map"
)

type RestClient struct {
	Clusters        []ServerSpec
	Provider        Provider
	Cm              *ContainerManager
	TopologyChanged bool
	nodeCache       cmap.ConcurrentMap
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
	Hostname          string
	ClusterMembership string
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

type ClusterInfo struct {
	Name  string
	Nodes []NodeSelf
}

type CollectionId struct {
	Uid string
}

func NewRestClient(clusters []ServerSpec, provider Provider, cm *ContainerManager) RestClient {
	rest := RestClient{
		Clusters:        clusters,
		Provider:        provider,
		Cm:              cm,
		TopologyChanged: true,
		nodeCache:       cmap.New(),
		IsWatching:      false,
	}

	return rest
}

func (r *RestClient) resetCache() {

	for k := range r.nodeCache.Items() {
		r.nodeCache.Remove(k)
	}
}

func (r *RestClient) WatchForTopologyChanges() {
	r.IsWatching = true
	r.resetCache()

	for {

		// wait before checking rebalance status
		time.Sleep(10 * time.Second)

		// reset cache if any of the clusters are rebalancing
		for _, cluster := range r.Clusters {
			orchestrator := cluster.Names[0]
			if r.ClusterIsRebalancing(orchestrator) {
				r.resetCache()
			}
		}
	}

	r.IsWatching = false
}

func (r *RestClient) GetServerVersion() string {
	host := r.GetOrchestrator()
	n := r.GetHostNodeSelf(host)
	return n.Version
}

func (r *RestClient) GetMemTotal(host string) int {
	n := r.getHostNodeSelf(host)
	q := n.MemoryTotal
	if q == 0 {
		time.Sleep(5 * time.Second)
		return r.GetMemTotal(host)
	}
	q = q / 1048576 // mb
	return q
}

func (r *RestClient) GetMemReserved(host string) int {
	n := r.getHostNodeSelf(host)
	q := n.McdMemoryReserved
	if q == 0 {
		time.Sleep(5 * time.Second)
		return r.GetMemReserved(host)
	}

	return q
}

func (r *RestClient) GetIndexQuota(host string) int {
	n := r.getHostNodeSelf(host)
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

	if val, ok := r.cacheGet("self", host); ok {
		return val.(NodeSelf)
	}
	return r.getHostNodeSelf(host)
}

func (r *RestClient) getHostNodeSelf(host string) NodeSelf {

	url := r.Provider.GetRestUrl(host)
	auth := r.GetAuth(host)
	n := r.GetNodeSelf(auth, url)
	r.cacheSet("self", host, n)
	return n
}

func (r *RestClient) GetHostNodeStatuses(host string) NodeStatuses {

	if val, ok := r.cacheGet("status", host); ok {
		return val.(NodeStatuses)
	}

	return r.getHostNodeStatuses(host)
}

func (r *RestClient) getHostNodeStatuses(host string) NodeStatuses {
	url := r.Provider.GetRestUrl(host)
	auth := r.GetAuth(host)
	n := r.GetNodeStatuses(auth, url)
	r.cacheSet("status", host, n)
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

func (r *RestClient) GetClusterInfo() ClusterInfo {
	host := r.GetOrchestrator()
	url := r.Provider.GetRestUrl(host)
	auth := r.GetAuth(host)
	reqUrl := fmt.Sprintf("%s/pools/default", url)
	var s ClusterInfo
	r.JsonRequest(auth, reqUrl, &s)
	return s
}

func (r *RestClient) IsNodeActive(host string) bool {
	cluster := r.GetClusterInfo()
	for i := 0; i < len(cluster.Nodes); i++ {
		ip := host + ":8091"
		if cluster.Nodes[i].Hostname == ip && cluster.Nodes[i].ClusterMembership == "active" {
			return true
		}
	}
	return false

}

//
func (r *RestClient) JsonRequest(auth, restUrl string, v interface{}) {
	// run curl container to make rest request
	cmd := []string{"-u", auth, "-s", restUrl, "-k"}
	id, svcId := r.Cm.RunRestContainer(cmd)
	//fmt.Println(MakeTaskMsg("appropriate/curl", id, cmd, false))
	// convert logs to json
	resp := r.Cm.GetLogs(id, "all")
	parseErr := StringToJson(resp, &v)
	// reset cache if we got a bad response
	// as this indicates unstable cluster
	if parseErr != nil {
		r.resetCache()
	}

	// remove container
	if r.Cm.ProviderType == "swarm" {
		err := r.Cm.RemoveService(svcId)
		logerr(err)
	} else {
		err := r.Cm.RemoveContainer(id)
		logerr(err)
	}
}

//
func (r *RestClient) JsonPostRequest(auth, restUrl, data string, v interface{}) {
	// run curl container to make rest request
	cmd := []string{"-u", auth, "-s", restUrl, "-d", data}
	id, svcId := r.Cm.RunRestContainer(cmd)
	fmt.Println(MakeTaskMsg("appropriate/curl", id, cmd, false))
	// convert logs to json
	resp := r.Cm.GetLogs(id, "all")
	//fmt.Println("response:", resp)
	parseErr := StringToJson(resp, &v)
	// reset cache if we got a bad response
	// as this indicates unstable cluster
	if parseErr != nil {
		r.resetCache()
	}

	// remove container
	if r.Cm.ProviderType == "swarm" {
		err := r.Cm.RemoveService(svcId)
		logerr(err)
	} else {
		err := r.Cm.RemoveContainer(id)
		logerr(err)
	}
}

func (r *RestClient) cacheGet(ctx, key string) (interface{}, bool) {
	cacheKey := fmt.Sprintf("%s/%s", ctx, key)
	return r.nodeCache.Get(cacheKey)
}

func (r *RestClient) cacheSet(ctx, key string, val interface{}) {
	cacheKey := fmt.Sprintf("%s/%s", ctx, key)
	r.nodeCache.Set(cacheKey, val)
}

func (r *RestClient) updateNumberOfBucktes(numberOfBuckets string) {
	host := r.GetOrchestrator()
	url := r.Provider.GetRestUrl(host)
	auth := r.GetAuth(host)
	reqUrl := fmt.Sprintf("%s/internalSettings", url)
	var s []string
	data := "maxBucketCount=" + numberOfBuckets
	r.JsonPostRequest(auth, reqUrl, data, &s)
}

func (r *RestClient) createScope(bucketName, scopeName string) {
	host := r.GetOrchestrator()
	url := r.Provider.GetRestUrl(host)
	auth := r.GetAuth(host)
	reqUrl := fmt.Sprintf("%s/pools/default/buckets/%s/scopes", url, bucketName)
	//fmt.Printf("URL: %s", reqUrl)
	var s CollectionId
	data := "name=" + scopeName
	r.JsonPostRequest(auth, reqUrl, data, &s)
}

func (r *RestClient) createCollections(bucketName, scopeName, collectionName string) {
	host := r.GetOrchestrator()
	url := r.Provider.GetRestUrl(host)
	auth := r.GetAuth(host)
	reqUrl := fmt.Sprintf("%s/pools/default/buckets/%s/scopes/%s/collections", url, bucketName, scopeName)
	//fmt.Printf("URL: %s", reqUrl)
	var s CollectionId
	data := "name=" + collectionName
	r.JsonPostRequest(auth, reqUrl, data, &s)
}

func (r *RestClient) updateMagmaMinMemoryQuota(magmaMinMemoryQuota string) {
	host := r.GetOrchestrator()
	url := r.Provider.GetRestUrl(host)
	auth := r.GetAuth(host)
	reqUrl := fmt.Sprintf("%s/internalSettings", url)
	var s []string
	data := "magmaMinMemoryQuota=" + magmaMinMemoryQuota
	r.JsonPostRequest(auth, reqUrl, data, &s)
}
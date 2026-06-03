package sequoia

import (
	"encoding/json"
	"fmt"
	cmap "github.com/streamrail/concurrent-map"
	"strconv"
	"strings"
	"time"
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

type PoolNodes struct {
	Name             string
	Nodes            []PoolNode
	FtsMemoryQuota   int
	IndexMemoryQuota int
	MemoryQuota      int
}

type PoolNode struct {
	MemoryTotal       int
	MemoryFree        int
	McdMemoryReserved int
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

type EncryptionKey struct {
	ID       string
	Name     string
	Type     string
	Usage    []string
	Data     map[string]interface{}
	RawValue map[string]interface{}
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
	defer func() {
		r.IsWatching = false
	}()

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

func (r *RestClient) getPoolNode(host string) PoolNode {
	if val, ok := r.cacheGet("pool/node/", host); ok {
		return val.(PoolNode)
	}
	url := r.Provider.GetRestUrl(host)
	auth := r.GetAuth(host)
	n := r.GetPoolNode(auth, url, host)
	r.cacheSet("pool/node/", host, n)
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

func (r *RestClient) GetPoolNode(auth, url, host string) PoolNode {
	reqUrl := fmt.Sprintf("%s/pools/nodes", url)
	var cluster PoolNodes
	var node PoolNode
	r.JsonRequest(auth, reqUrl, &cluster)
	index_str := strings.Split(host, ".")[0]
	index := strings.Split(index_str, "-")[1]
	index_int, _ := strconv.Atoi(index)
	node = cluster.Nodes[index_int-1]
	return node
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

func (r *RestClient) GetEncryptionKeys(host string) ([]EncryptionKey, error) {
	url := fmt.Sprintf("%s/settings/encryptionKeys", r.Provider.GetRestUrl(host))
	auth := r.GetAuth(host)
	cmd := []string{"-u", auth, "-s", "-k",
		"-w", "\nHTTP_STATUS:%{http_code}\n",
		url,
	}
	id, svcId := r.Cm.RunRestContainer(cmd)
	resp := r.Cm.GetLogs(id, "all")

	var decoded interface{}
	trimmed := extractJSONPayload(resp)
	if err := json.Unmarshal([]byte(trimmed), &decoded); err != nil {
		cleanupRestContainer(r.Cm, id, svcId)
		return nil, err
	}

	keys := flattenEncryptionKeys(decoded)
	cleanupRestContainer(r.Cm, id, svcId)
	return keys, nil
}

func (r *RestClient) CreateEncryptionKey(host string, payload []byte) error {
	url := fmt.Sprintf("%s/settings/encryptionKeys", r.Provider.GetRestUrl(host))
	auth := r.GetAuth(host)
	cmd := []string{"-u", auth, "-s", "-k",
		"-w", "\nHTTP_STATUS:%{http_code}\n",
		"-X", "POST",
		"-H", "Content-Type: application/json",
		url, "-d", string(payload),
	}
	fmt.Printf("[CreateEncryptionKey] POST %s \n", url)
	id, svcId := r.Cm.RunRestContainer(cmd)
	resp := r.Cm.GetLogs(id, "all")
	fmt.Printf("[CreateEncryptionKey] response: %s\n", strings.TrimSpace(resp))
	cleanupRestContainer(r.Cm, id, svcId)
	if !strings.Contains(resp, "HTTP_STATUS:200") {
		return fmt.Errorf("CreateEncryptionKey: non-200 response: %s", strings.TrimSpace(resp))
	}
	return nil
}

func (r *RestClient) PutEncryptionKey(host, keyID string, payload []byte) error {
	url := fmt.Sprintf("%s/settings/encryptionKeys/%s", r.Provider.GetRestUrl(host), keyID)
	auth := r.GetAuth(host)
	cmd := []string{"-u", auth, "-s", "-k",
		"-w", "\nHTTP_STATUS:%{http_code}\n",
		"-X", "PUT",
		"-H", "Content-Type: application/json",
		url, "-d", string(payload),
	}
	fmt.Printf("[PutEncryptionKey] PUT %s payload=%s\n", url, string(payload))
	id, svcId := r.Cm.RunRestContainer(cmd)
	resp := r.Cm.GetLogs(id, "all")
	fmt.Printf("[PutEncryptionKey] response: %s\n", strings.TrimSpace(resp))
	cleanupRestContainer(r.Cm, id, svcId)
	if !strings.Contains(resp, "HTTP_STATUS:200") {
		return fmt.Errorf("PutEncryptionKey: non-200 response: %s", strings.TrimSpace(resp))
	}
	return nil
}

func (r *RestClient) ConfigureOtherEncryptionAtRest(host string, payload []byte) error {
	url := fmt.Sprintf("%s/settings/security/encryptionAtRest/other", r.Provider.GetRestUrl(host))
	auth := r.GetAuth(host)
	cmd := []string{"-u", auth, "-s", "-k",
		"-w", "\nHTTP_STATUS:%{http_code}\n",
		"-X", "POST",
		"-H", "Content-Type: application/json",
		url, "-d", string(payload),
	}
	fmt.Printf("[ConfigureOtherEncryptionAtRest] POST %s payload=%s\n", url, string(payload))
	id, svcId := r.Cm.RunRestContainer(cmd)
	resp := r.Cm.GetLogs(id, "all")
	fmt.Printf("[ConfigureOtherEncryptionAtRest] response: %s\n", strings.TrimSpace(resp))
	cleanupRestContainer(r.Cm, id, svcId)
	if !strings.Contains(resp, "HTTP_STATUS:200") {
		return fmt.Errorf("ConfigureOtherEncryptionAtRest: non-200 response: %s", strings.TrimSpace(resp))
	}
	return nil
}

func cleanupRestContainer(cm *ContainerManager, id, svcId string) {
	if cm.ProviderType == "swarm" {
		err := cm.RemoveService(svcId)
		logerr(err)
	} else {
		err := cm.RemoveContainer(id)
		logerr(err)
	}
}

func extractJSONPayload(resp string) string {
	start := strings.Index(resp, "{")
	arrayStart := strings.Index(resp, "[")
	if start == -1 || (arrayStart != -1 && arrayStart < start) {
		start = arrayStart
	}
	if start == -1 {
		return resp
	}
	end := strings.LastIndexAny(resp, "}]")
	if end == -1 || end < start {
		return resp[start:]
	}
	return resp[start : end+1]
}

func flattenEncryptionKeys(decoded interface{}) []EncryptionKey {
	keys := []EncryptionKey{}
	switch v := decoded.(type) {
	case []interface{}:
		for _, item := range v {
			if key, ok := encryptionKeyFromMap(item); ok {
				keys = append(keys, key)
			}
			if m, ok := item.(map[string]interface{}); ok {
				if dataMap, ok := m["data"].(map[string]interface{}); ok {
					if arr, ok := dataMap["keys"].([]interface{}); ok {
						for _, nested := range arr {
							if key, ok := encryptionKeyFromMap(nested); ok {
								keys = append(keys, key)
							}
						}
					}
				}
			}
		}
	case map[string]interface{}:
		for _, candidate := range []interface{}{v["keys"], v["data"], v["results"], v["encryptionKeys"]} {
			if arr, ok := candidate.([]interface{}); ok {
				for _, item := range arr {
					if key, ok := encryptionKeyFromMap(item); ok {
						keys = append(keys, key)
					}
				}
			} else if m, ok := candidate.(map[string]interface{}); ok {
				if arr, ok := m["keys"].([]interface{}); ok {
					for _, item := range arr {
						if key, ok := encryptionKeyFromMap(item); ok {
							keys = append(keys, key)
						}
					}
				}
			}
		}
	}
	return keys
}

func encryptionKeyFromMap(item interface{}) (EncryptionKey, bool) {
	m, ok := item.(map[string]interface{})
	if !ok {
		return EncryptionKey{}, false
	}
	key := EncryptionKey{
		RawValue: m,
	}
	for _, field := range []string{"id", "secretId", "keyId"} {
		if v, ok := m[field]; ok && key.ID == "" {
			key.ID = fmt.Sprintf("%v", v)
		}
	}
	if v, ok := m["name"]; ok {
		key.Name = fmt.Sprintf("%v", v)
	}
	if v, ok := m["type"]; ok {
		key.Type = fmt.Sprintf("%v", v)
	}
	if v, ok := m["usage"]; ok {
		switch usages := v.(type) {
		case []interface{}:
			for _, usage := range usages {
				key.Usage = append(key.Usage, fmt.Sprintf("%v", usage))
			}
		case []string:
			key.Usage = append(key.Usage, usages...)
		}
	}
	if v, ok := m["data"]; ok {
		if dataMap, ok := v.(map[string]interface{}); ok {
			key.Data = dataMap
		}
	}
	return key, true
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

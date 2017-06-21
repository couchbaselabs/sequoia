package sequoia

import (
	"encoding/json"
	"io/ioutil"

	"fmt"
)

// MobileHostDefinition is the expected format for the json
// host file defintion
type MobileHostDefinition struct {
	Hosts            []map[string]string `json:"hosts"`
	Environment      map[string]bool     `json:"environment"`
	CouchbaseServers []map[string]string `json:"couchbase_servers"`
	SyncGateways     []map[string]string `json:"sync_gateways"`
	SgAccels         []map[string]string `json:"sg_accels"`
	LoadBalancers    []map[string]string `json:"load_balancers"`
	LoadGenerators   []map[string]string `json:"load_generators"`
}

// GenerateMobileHostDefinition Write a json representation of the
// running services to all mobile-testkit to run functional tests
// against Sync Gateway
func GenerateMobileHostDefinition(s *Scope) {

	// Add Couchbase Servers to host file
	var hosts []map[string]string
	var couchbaseServerHosts []map[string]string
	count := 1
	for _, serverSpec := range s.Spec.Servers {
		for _, name := range serverSpec.Names {
			hostEntry := make(map[string]string)
			hostEntry["name"] = fmt.Sprintf("cbs%d", count)
			hostEntry["ip"] = name
			couchbaseServerHosts = append(couchbaseServerHosts, hostEntry)
			hosts = append(hosts, hostEntry)
			count++
		}
	}

	// Add Sync Gateways to host file
	count = 1
	var syncGatewayHosts []map[string]string
	for _, syncGatewaySpec := range s.Spec.SyncGateways {
		for _, name := range syncGatewaySpec.Names {
			hostEntry := make(map[string]string)
			hostEntry["name"] = fmt.Sprintf("sg%d", count)
			hostEntry["ip"] = name
			syncGatewayHosts = append(syncGatewayHosts, hostEntry)
			hosts = append(hosts, hostEntry)
			count++
		}
	}

	environment := map[string]bool{
		"xattrs_enabled":  false,
		"cbs_ssl_enabled": false,
	}

	// TODO: SgAccels, LoadBalancers, LoadGenerators
	hostDef := MobileHostDefinition{
		Hosts:            hosts,
		Environment:      environment,
		CouchbaseServers: couchbaseServerHosts,
		SyncGateways:     syncGatewayHosts,
		SgAccels:         []map[string]string{},
		LoadBalancers:    []map[string]string{},
		LoadGenerators:   []map[string]string{},
	}

	// Convert definition to json
	jsonDef, err := json.MarshalIndent(hostDef, "", "    ")
	chkerr(err)

	// Create a host file in cwd
	err = ioutil.WriteFile("hosts.json", jsonDef, 0644)
	chkerr(err)
}

package sequoia

import (
	"fmt"
	"strings"
)

type BucketSpec struct {
	Name      string
	Names     []string
	Count     uint8
	Ram       string
	Replica   uint8
	Type      string
	Sasl      string
	Eviction  string
	DDoc      string
	DDocViews map[string][]ViewSpec
}

type ServerSpec struct {
	Name         string
	Names        []string
	Count        uint8
	Ram          string
	IndexRam     string `yaml:"index_ram"`
	FtsRam       string `yaml:"fts_ram"`
	RestUsername string `yaml:"rest_username"`
	RestPassword string `yaml:"rest_password"`
	RestPort     string `yaml:"rest_port"`
	ViewPort     string `yaml:"view_port"`
	QueryPort    string `yaml:"query_port"`
	InitNodes    uint8  `yaml:"init_nodes"`
	DataPath     string `yaml:"data_path"`
	IndexPath    string `yaml:"index_path"`
	IndexStorage string `yaml:"index_storage"`
	Buckets      string
	BucketSpecs  []BucketSpec
	NodesActive  uint8
	Services     map[string]uint8
	NodeServices map[string][]string
}

type ViewSpec struct {
	DDoc   string
	View   string
	Map    string
	Reduce string
}

type ScopeSpec struct {
	Buckets []BucketSpec
	Servers []ServerSpec
	Views   []ViewSpec
}

func (s *ServerSpec) InitNodeServices() {

	var i uint8
	numNodes := s.Count
	numIndexNodes := s.Services["index"]
	numQueryNodes := s.Services["query"]
	numFtsNodes := s.Services["fts"]
	numDataNodes := s.Services["data"]
	customIndexStart := s.Services["index_start"]
	customQueryStart := s.Services["query_start"]
	customFtsStart := s.Services["fts_start"]

	s.NodeServices = make(map[string][]string)

	// Spread Strategy
	// make first set of nodes data
	// and second set index to avoid
	// overlapping if possible when specific
	// number of service types provided
	indexStartPos := numNodes - numQueryNodes - numIndexNodes
	if customIndexStart > 0 {
		// override
		indexStartPos = customIndexStart - 1
	}
	if indexStartPos > numNodes {
		indexStartPos = 0
	}

	// fts defaults on same box as index machine
	// override with fts_start
	ftsStartPos := indexStartPos
	if customFtsStart > 0 {
		// override
		ftsStartPos = customFtsStart - 1
	}
	if ftsStartPos > numNodes {
		ftsStartPos = 0
	}

	queryStartPos := numNodes - numQueryNodes
	if customQueryStart > 0 {
		// override
		queryStartPos = customQueryStart - 1
	}
	if queryStartPos > numNodes {
		queryStartPos = 0
	}

	for i = 0; i < numNodes; i = i + 1 {
		name := s.Names[i]
		s.NodeServices[name] = []string{}
		if i >= indexStartPos && numIndexNodes > 0 {
			s.NodeServices[name] = append(s.NodeServices[name], "index")
			numIndexNodes--
		}
		if i >= ftsStartPos && numFtsNodes > 0 {
			s.NodeServices[name] = append(s.NodeServices[name], "fts")
			numFtsNodes--
		}
		if i >= queryStartPos && numQueryNodes > 0 {
			s.NodeServices[name] = append(s.NodeServices[name], "query")
			numQueryNodes--
		}
		if numDataNodes > 0 {
			s.NodeServices[name] = append(s.NodeServices[name], "data")
			numDataNodes--
		} else if i == 0 { // must add data to orchestrator
			s.NodeServices[name] = append(s.NodeServices[name], "data")
		}

		// must have at least data service
		if len(s.NodeServices[name]) == 0 {
			s.NodeServices[name] = append(s.NodeServices[name], "data")
		}
	}
}

func (s *ScopeSpec) ApplyToAllServers(operation func(string, *ServerSpec)) {
	s.ApplyToServers(operation, 0, 0)
}

func (s *ScopeSpec) ApplyToServers(operation func(string, *ServerSpec),
	startIdx int, endIdx int) {

	useLen := false
	if endIdx == 0 {
		useLen = true
	}

	for i, server := range s.Servers {
		if useLen {
			endIdx = len(server.Names)
		}
		for _, serverName := range server.Names[startIdx:endIdx] {
			operation(serverName, &server)
			s.Servers[i] = server // allowed apply func to modify server
		}
	}
}

func (s *ScopeSpec) ToAttr(attr string) string {

	switch attr {

	case "rest_username":
		return "RestUsername"
	case "rest_password":
		return "RestPassword"
	case "name":
		return "Name"
	case "ram":
		return "Ram"
	case "rest_port":
		return "RestPort"
	case "view_port":
		return "ViewPort"
	case "query_port":
		return "QueryPort"
	}

	return ""
}

func (s *ScopeSpec) ForCluster(name string) ServerSpec {
	var spec ServerSpec
	for _, cluster := range s.Servers {
		if cluster.Name == name {
			spec = cluster
			break
		}
	}
	return spec
}

func NewScopeSpec(fileName string) ScopeSpec {

	var spec ScopeSpec
	if strings.Index(fileName, ".ini") > 0 {
		spec = SpecFromIni(fileName)
	} else {
		spec = SpecFromYaml(fileName)
	}

	return spec
}

func SpecFromYaml(fileName string) ScopeSpec {
	var spec ScopeSpec
	// init from yaml
	ReadYamlFile(fileName, &spec)

	// map ddocs to views
	ddocViewMap := make(map[string][]ViewSpec)
	for _, view := range spec.Views {
		// add views to this ddoc
		ddocViewMap[view.DDoc] = append(ddocViewMap[view.DDoc], view)
	}

	// init bucket section of spec
	bucketNameMap := make(map[string]BucketSpec)
	for i, bucket := range spec.Buckets {
		spec.Buckets[i].Names = ExpandName(bucket.Name, bucket.Count)
		if spec.Buckets[i].Type == "" {
			spec.Buckets[i].Type = "couchbase"
		}
		if spec.Buckets[i].Replica == 0 {
			spec.Buckets[i].Replica = 1
		}
		spec.Buckets[i].DDocViews = make(map[string][]ViewSpec)
		if bucket.DDoc != "" {
			if views, ok := ddocViewMap[bucket.DDoc]; ok == true {
				spec.Buckets[i].DDocViews[bucket.DDoc] = views
			}
		}
		bucketNameMap[bucket.Name] = spec.Buckets[i]
	}

	// init server section of spec
	for i, server := range spec.Servers {
		spec.Servers[i].Names = ExpandName(server.Name, server.Count)
		spec.Servers[i].BucketSpecs = make([]BucketSpec, 0)
		// map server buckets to bucket objects
		bucketList := strings.Split(spec.Servers[i].Buckets, ",")
		for _, bucketName := range bucketList {
			if bucketSpec, ok := bucketNameMap[bucketName]; ok {
				spec.Servers[i].BucketSpecs = append(spec.Servers[i].BucketSpecs, bucketSpec)
			}
		}
		// init node services
		spec.Servers[i].InitNodeServices()
	}

	return spec
}

func SpecFromIni(fileName string) ScopeSpec {
	spec := ScopeSpec{
		Servers: []ServerSpec{},
		Buckets: []BucketSpec{},
	}
	cfg := ReadIniFile(fileName)

	// clusters are sections of servers (not named [servers])
	// servers
	serverSpec := ServerSpec{
		NodeServices: make(map[string][]string),
		Names:        []string{},
	}
	clusterName := RandStr(6)
	serverSpec.Name = clusterName + ".st.couchbase.com"
	for i, serverKey := range cfg.Section("servers").Keys() {
		serverSpec.Count = uint8(i + 1)
		name := fmt.Sprintf("%s-%d.st.couchbase.com",
			clusterName,
			serverSpec.Count)
		serverSpec.Names = append(serverSpec.Names, name)
		section := cfg.Section(serverKey.String())
		if username := section.Key("rest_username"); username.String() != "" {
			serverSpec.RestUsername = username.String()
		} else {
			serverSpec.RestUsername = "Administrator"
		}
		if password := section.Key("rest_password"); password.String() != "" {
			serverSpec.RestPassword = password.String()
		} else {
			serverSpec.RestPassword = "password"
		}
		if services := section.Key("services"); services.String() != "" {
			svcString := services.String()
			svcString = strings.Replace(svcString, "kv", "data", 1)
			svcString = strings.Replace(svcString, "n1ql", "query", 1)
			serverSpec.NodeServices[name] = strings.Split(svcString, ",")
		}
		serverSpec.Ram = "60%"
	}
	serverSpec.InitNodes = serverSpec.Count
	spec.Servers = append(spec.Servers, serverSpec)
	return spec

}

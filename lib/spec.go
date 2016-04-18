package sequoia

import (
	"log"
	"strings"
)

type Config struct {
	Client   string
	Scope    string
	Test     string
	Provider string
	Build    string
	Options  ConfigOpts
}

type ConfigOpts struct {
	SkipSetup    bool `yaml:"skip_setup"`
	SkipTest     bool `yaml:"skip_test"`
	SkipTeardown bool `yaml:"skip_teardown"`
	Repeat       int
	Scale        int
}

func NewConfigSpec(fileName *string, scopeFile *string, testFile *string) Config {
	var config Config
	ReadYamlFile(*fileName, &config)

	// allow overrides
	if *scopeFile != "" {
		config.Scope = *scopeFile
	}
	if *testFile != "" {
		config.Test = *testFile
	}

	// verify
	if config.Scope == "" {
		log.Fatalln("Config Error: scope file required, use -scope or specify in config.yml")
	}
	if config.Test == "" {
		log.Fatalln("Config Error: test file required, use -test or specify in config.yml")
	}

	if config.Build == "" {
		config.Build = "latest"
	}

	return config
}

type BucketSpec struct {
	Name     string
	Names    []string
	Count    uint8
	Ram      string
	Replica  uint8
	Type     string
	Sasl     string
	Eviction string
}

type ServerSpec struct {
	Name         string
	Names        []string
	Count        uint8
	Ram          string
	IndexRam     string `yaml:"index_ram"`
	RestUsername string `yaml:"rest_username"`
	RestPassword string `yaml:"rest_password"`
	RestPort     string `yaml:"rest_port"`
	ViewPort     string `yaml:"view_port"`
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

func (s *ServerSpec) InitNodeServices() {

	var i uint8
	numNodes := s.Count
	numIndexNodes := s.Services["index"]
	numQueryNodes := s.Services["query"]
	numDataNodes := s.Services["data"]
	s.NodeServices = make(map[string][]string)

	// Spread Strategy
	// make first set of nodes data
	// and second set index to avoid
	// overlapping if possible when specific
	// number of service types provided
	indexStartPos := numNodes - numQueryNodes - numIndexNodes
	if indexStartPos < 0 {
		indexStartPos = 0
	}

	queryStartPos := numNodes - numQueryNodes
	if queryStartPos < 0 {
		queryStartPos = 0
	}

	for i = 0; i < numNodes; i = i + 1 {
		name := s.Names[i]
		s.NodeServices[name] = []string{}
		if i >= indexStartPos && numIndexNodes > 0 {
			s.NodeServices[name] = append(s.NodeServices[name], "index")
			numIndexNodes--
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

type ScopeSpec struct {
	Buckets []BucketSpec
	Servers []ServerSpec
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

	// init from yaml
	var spec ScopeSpec
	ReadYamlFile(fileName, &spec)

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

		if spec.Servers[i].ViewPort == "" {
			spec.Servers[i].ViewPort = "8092"
		}
	}

	return spec
}

package sequoia

import (
	"fmt"
	"github.com/fatih/color"
	"gopkg.in/yaml.v2"
	"io/ioutil"
	"strings"
)

type Config struct {
	Client   string
	Scope    string
	Test     string
	Provider string
}

func NewConfigSpec(fileName string) Config {
	var config Config
	ReadYamlFile(fileName, &config)
	return config
}

type BucketSpec struct {
	Name     string
	Names    []string
	Count    uint8
	Ram      uint32
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
	RestUsername string `yaml:"rest_username"`
	RestPassword string `yaml:"rest_password"`
	RestPort     string `yaml:"rest_port"`
	InitNodes    uint8  `yaml:"init_nodes"`
	Services     string
	Buckets      string
	BucketSpecs  []BucketSpec
	NodesActive  uint8
}

type ScopeSpec struct {
	Buckets []BucketSpec
	Servers []ServerSpec
}

func (s *ScopeSpec) ApplyToAllServers(operation func(string, ServerSpec)) {
	s.ApplyToServers(operation, 0, 0)
}

func (s *ScopeSpec) ApplyToServers(operation func(string, ServerSpec),
	startIdx int, endIdx int) {

	for _, server := range s.Servers {
		if endIdx == 0 {
			endIdx = len(server.Names)
		}
		for _, serverName := range server.Names[startIdx:endIdx] {
			operation(serverName, server)
		}
	}
}

func NewScopeSpec(fileName string) ScopeSpec {

	// init from yaml
	var scope ScopeSpec
	ReadYamlFile(fileName, &scope)

	// init bucket section of scope
	bucketNameMap := make(map[string]BucketSpec)
	for i, bucket := range scope.Buckets {
		scope.Buckets[i].Names = ExpandName(bucket.Name, bucket.Count)
		if scope.Buckets[i].Type == "" {
			scope.Buckets[i].Type = "couchbase"
		}
		if scope.Buckets[i].Replica == 0 {
			scope.Buckets[i].Replica = 1
		}
		bucketNameMap[bucket.Name] = scope.Buckets[i]
	}

	// init server section of scope
	for i, server := range scope.Servers {
		scope.Servers[i].Names = ExpandName(server.Name, server.Count)
		scope.Servers[i].BucketSpecs = make([]BucketSpec, 0)

		// map server buckets to bucket objects
		bucketList := strings.Split(scope.Servers[i].Buckets, ",")
		for _, bucketName := range bucketList {
			if bucketSpec, ok := bucketNameMap[bucketName]; ok {
				scope.Servers[i].BucketSpecs = append(scope.Servers[i].BucketSpecs, bucketSpec)
			}
		}
	}

	return scope
}

func ExpandName(name string, count uint8) []string {
	names := make([]string, count)
	var i uint8

	if count == 1 {
		names[0] = name
	} else {
		for i = 1; i <= count; i++ {
			parts := strings.Split(name, ".")
			fqn := fmt.Sprintf("%s-%d", parts[0], i)
			if len(parts) > 1 {
				parts[0] = fqn
				fqn = strings.Join(parts, ".")
			}
			names[i-1] = fqn
		}
	}
	return names
}

func ReadYamlFile(filename string, spec interface{}) {
	source, err := ioutil.ReadFile(filename)
	chkerr(err)

	err = yaml.Unmarshal(source, spec)
	chkerr(err)
	fmt.Println(color.GreenString("\u2713 "), color.WhiteString("ok %s", filename))
}

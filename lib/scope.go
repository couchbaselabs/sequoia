package sequoia

/* Scope.go
 *
 * Reads in scope spec file and defines
 * methods to configure scope.
 *
 * The scope Object includes a container manager
 * for creating containers required for setup
 * and a reference to Provider that offers
 * couchbase resources.
 *
 */

import (
	"fmt"
	"reflect"
	"regexp"
	"strconv"
	"strings"
)

type Scope struct {
	Spec       ScopeSpec
	Cm         *ContainerManager
	Provider   Provider
	TestConfig Config
}

func NewScope(config Config) Scope {

	// init from yaml
	spec := NewScopeSpec(config.Scope)

	// set container manager to use provisioning scope
	cm := NewContainerManager(config.Client)

	// create provider of resources for scope
	provider := NewProvider(config, spec.Servers)
	return Scope{
		spec,
		cm,
		provider,
		config,
	}
}

func (s *Scope) Setup() {

	s.Provider.ProvideCouchbaseServers(s.Spec.Servers)
	s.WaitForNodes()
	s.InitNodes()
	s.InitCluster()
	s.AddNodes()
	s.RebalanceClusters()
	s.CreateBuckets()
}

func (s *Scope) TearDown() {
	s.Cm.RemoveAllContainers()
}

func (s *Scope) WaitForNodes() {

	var image = "martin/wait"

	// use martin/wait container to wait for node to listen on port 8091
	waitForNodesOp := func(name string, server *ServerSpec) {
		ip := fmt.Sprintf("%s:%d", s.Provider.GetHostAddress(name), 8091)
		command := []string{"-c", ip, "-t", "120"}
		desc := "wait for " + ip
		task := ContainerTask{
			Describe: desc,
			Image:    image,
			Command:  command,
			Async:    false,
		}
		if s.Provider.GetType() == "docker" {
			task.LinksTo = name
		}

		s.Cm.Run(task)
	}

	// verify nodes
	s.Spec.ApplyToAllServers(waitForNodesOp)

}

func (s *Scope) InitNodes() {

	var image = "couchbase-cli"

	initNodesOp := func(name string, server *ServerSpec) {
		ip := s.Provider.GetHostAddress(name)
		command := []string{"node-init",
			"-c", ip,
			"-u", server.RestUsername,
			"-p", server.RestPassword,
		}

		if server.DataPath != "" {
			command = append(command, "--node-init-data-path", server.DataPath)
		}
		if server.IndexPath != "" {
			command = append(command, "--node-init-index-path", server.IndexPath)
		}
		desc := "init node " + ip
		task := ContainerTask{
			Describe: desc,
			Image:    image,
			Command:  command,
			Async:    false,
		}
		if s.Provider.GetType() == "docker" {
			task.LinksTo = name
		}

		s.Cm.Run(task)
	}

	// verify nodes
	s.Spec.ApplyToAllServers(initNodesOp)
}

func (s *Scope) InitCluster() {

	var image = "couchbase-cli"

	initClusterOp := func(name string, server *ServerSpec) {
		orchestrator := server.Names[0]
		ip := s.Provider.GetHostAddress(orchestrator)
		servicesList := server.NodeServices[name]
		services := strings.Join(servicesList, ",")
		ramQuota := server.Ram
		if ramQuota == "" {
			// use cluster mcdReserved
			memTotal := s.ClusterMemReserved(name, server)
			ramQuota = strconv.Itoa(memTotal)
		}
		if strings.Index(ramQuota, "%") > -1 {
			// use percentage of memtotal
			memTotal := s.ClusterMemTotal(name, server)
			ramQuota = strings.Replace(ramQuota, "%", "", 1)
			ramVal, _ := strconv.Atoi(ramQuota)
			ramQuota = strconv.Itoa((memTotal * ramVal) / 100)
		}

		// update ramQuota in case modified
		server.Ram = ramQuota
		command := []string{"cluster-init",
			"-c", ip,
			"-u", server.RestUsername,
			"-p", server.RestPassword,
			"--cluster-username", server.RestUsername,
			"--cluster-password", server.RestPassword,
			"--cluster-port", server.RestPort,
			"--cluster-ramsize", server.Ram,
			"--services", services,
		}
		if server.IndexRam != "" {
			command = append(command, "--cluster-index-ramsize", server.IndexRam)
		}
		if server.IndexStorage != "" {
			command = append(command, "--index-storage-setting", server.IndexStorage)
		}
		desc := "init cluster " + orchestrator
		task := ContainerTask{
			Describe: desc,
			Image:    image,
			Command:  command,
			Async:    false,
		}
		if s.Provider.GetType() == "docker" {
			task.LinksTo = orchestrator
		}
		s.Cm.Run(task)
		server.NodesActive++

	}

	// apply only to orchestrator
	s.Spec.ApplyToServers(initClusterOp, 0, 1)

}

func (s *Scope) AddNodes() {

	var image = "couchbase-cli"

	addNodesOp := func(name string, server *ServerSpec) {

		if server.InitNodes <= server.NodesActive {
			return
		}
		orchestrator := server.Names[0]
		orchestratorIp := s.Provider.GetHostAddress(orchestrator)
		ip := s.Provider.GetHostAddress(name)

		if name == orchestrator {
			return // not adding self
		}

		servicesList := server.NodeServices[name]
		services := strings.Join(servicesList, ",")
		command := []string{"server-add",
			"-c", orchestratorIp,
			"-u", server.RestUsername,
			"-p", server.RestPassword,
			"--server-add", ip,
			"--server-add-username", server.RestUsername,
			"--server-add-password", server.RestPassword,
			"--services", services,
		}

		desc := "add node " + ip
		task := ContainerTask{
			Describe: desc,
			Image:    image,
			Command:  command,
			Async:    false,
		}
		if s.Provider.GetType() == "docker" {
			task.LinksTo = orchestrator
		}

		s.Cm.Run(task)
		server.NodesActive++

	}

	// add nodes
	s.Spec.ApplyToAllServers(addNodesOp)
}

func (s *Scope) RebalanceClusters() {

	var image = "couchbase-cli"
	// configure rebalance operation
	operation := func(name string, server *ServerSpec) {

		orchestrator := server.Names[0]
		orchestratorIp := s.Provider.GetHostAddress(orchestrator)

		command := []string{"rebalance",
			"-c", orchestratorIp,
			"-u", server.RestUsername,
			"-p", server.RestPassword,
		}
		desc := "rebalance cluster " + orchestratorIp
		task := ContainerTask{
			Describe: desc,
			Image:    image,
			Command:  command,
			Async:    false,
		}
		if s.Provider.GetType() == "docker" {
			task.LinksTo = orchestrator
		}

		s.Cm.Run(task)
	}

	// apply only to orchestrator
	s.Spec.ApplyToServers(operation, 0, 1)

}

func (s *Scope) CreateBuckets() {

	var image = "couchbase-cli"

	// configure rebalance operation
	operation := func(name string, server *ServerSpec) {

		orchestrator := server.Names[0]
		ip := s.Provider.GetHostAddress(orchestrator)

		for _, bucket := range server.BucketSpecs {
			for _, bucketName := range bucket.Names {
				ramQuota := bucket.Ram
				if strings.Index(ramQuota, "%") > -1 {
					// convert ram to value
					ramQuota = strings.Replace(ramQuota, "%", "", 1)
					ramVal, _ := strconv.Atoi(ramQuota)
					nodeRam, _ := strconv.Atoi(server.Ram)
					ramQuota = strconv.Itoa((nodeRam * ramVal) / 100)
				}
				command := []string{"bucket-create", "-c", ip,
					"-u", server.RestUsername, "-p", server.RestPassword,
					"--bucket", bucketName,
					"--bucket-ramsize", ramQuota,
					"--bucket-type", bucket.Type,
					"--bucket-replica", strconv.Itoa(int(bucket.Replica)),
					"--enable-flush", "1", "--wait",
				}
				if bucket.Sasl != "" {
					command = append(command, "--bucket-password", bucket.Sasl)
				}
				if bucket.Eviction != "" {
					command = append(command, "--bucket-eviction-policy", bucket.Eviction)
				}

				desc := "bucket create " + bucketName
				task := ContainerTask{
					Describe: desc,
					Image:    image,
					Command:  command,
					Async:    false,
				}
				if s.Provider.GetType() == "docker" {
					task.LinksTo = orchestrator
				}

				s.Cm.Run(task)
			}
		}
	}

	// apply only to orchestrator
	s.Spec.ApplyToServers(operation, 0, 1)

}

func (s *Scope) ClusterMemTotal(name string, server *ServerSpec) int {
	rest := s.Provider.GetRestUrl(name)
	mem := GetMemTotal(rest, server.RestUsername, server.RestPassword)
	return mem
}

func (s *Scope) ClusterMemReserved(name string, server *ServerSpec) int {
	rest := s.Provider.GetRestUrl(name)
	mem := GetMemReserved(rest, server.RestUsername, server.RestPassword)
	return mem
}

func (s *Scope) CompileCommand(actionCommand string) []string {

	// remove extraneous white space
	re := regexp.MustCompile(`\s+`)
	actionCommand = re.ReplaceAllString(actionCommand, " ")

	idx := strings.Index(actionCommand, "$")
	for idx > -1 {
		fStart := strings.Index(actionCommand, "(")
		fEnd := strings.Index(actionCommand, ")")
		method := actionCommand[idx+1 : fStart]
		args := actionCommand[fStart+1 : fEnd]
		value := s.Resolve(method, args)
		actionCommand = strings.Replace(
			actionCommand,
			actionCommand[idx:fEnd+1],
			value, 1,
		)
		idx = strings.Index(actionCommand, "$")
	}

	// translate into in slice
	command := strings.Split(actionCommand, " ")

	commandFinal := []string{}

	// keep single quotes in tact
	var lastSingleQuote int = -1
	for i, v := range command {
		if strings.Index(v, "'") > -1 {
			// stash val until we reach another single quote
			if lastSingleQuote == -1 {
				// first quote
				lastSingleQuote = i
			} else {
				// ending quote
				var quotedString = []string{}
				for j := lastSingleQuote; j <= i; j++ {
					c := strings.Replace(command[j], "'", "", 1)
					quotedString = append(quotedString, c)
				}
				// append to command as fully quoted string
				commandFinal = append(commandFinal, strings.Join(quotedString, " "))
				lastSingleQuote = -1
			}
		} else {
			// just append value if not within single quote
			if lastSingleQuote == -1 {
				commandFinal = append(commandFinal, v)
			}
		}
	}

	return commandFinal
}

func (s *Scope) Resolve(method string, args string) string {
	switch method {

	case "address":
		argv := strings.Split(args, ",")
		cluster, _ := strconv.Atoi(argv[0])
		node, _ := strconv.Atoi(argv[1])
		scopeName := s.Spec.Servers[cluster].Names[node]
		address := s.Provider.GetHostAddress(scopeName)
		return address

	case "bucket":
		argv := strings.Split(args, ",")
		set, _ := strconv.Atoi(argv[0])
		index, _ := strconv.Atoi(argv[1])
		bucket := s.Spec.Buckets[set].Names[index]
		return bucket

	case "attr":
		argv := strings.Split(args, ",")
		cluster, _ := strconv.Atoi(argv[0])
		attr := strings.TrimSpace(argv[1])
		attr = s.Spec.ToAttr(attr)
		spec := reflect.ValueOf(s.Spec.Servers[cluster])
		val := spec.FieldByName(attr).String()
		return val

	case "toscale": // ie.. $toscale(10)
		attr, _ := strconv.Atoi(args)
		scale := s.TestConfig.Options.Scale
		if scale == 0 {
			scale++
		}
		val := strconv.Itoa(attr * scale)
		return val

	case "service": // ie.. $service(kv, 0, *)
		var argv = strings.Split(args, ",")
		service := strings.TrimSpace(argv[0])
		cluster := strings.TrimSpace(argv[1])
		var val string = fmt.Sprintf("<service_%s_node_not_found>", service)
		var idx int = 0
		if len(argv) == 3 { // override  which node to choose
			idx, _ = strconv.Atoi(strings.TrimSpace(argv[2]))
		}

		serverSpec := s.Spec.ForCluster(cluster)
		for _, name := range serverSpec.Names {
			rest := s.Provider.GetRestUrl(name)
			ok := NodeHasService(service, rest, serverSpec.RestUsername, serverSpec.RestPassword)
			if ok == true {
				if idx > 0 {
					idx--
				} else {
					// done found node with service
					val = s.Provider.GetHostAddress(name)
					break
				}
			}
		}

		return val
	}

	return ""
}

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
	"regexp"
	"strconv"
	"strings"

	"github.com/streamrail/concurrent-map"
)

type Scope struct {
	Spec     ScopeSpec
	Cm       *ContainerManager
	Provider Provider
	Flags    TestFlags
	Version  string
	Vars     cmap.ConcurrentMap
	Loops    int
	Rest     RestClient
}

func NewScope(flags TestFlags, cm *ContainerManager) Scope {

	// init from yaml or ini
	spec := NewScopeSpec(*flags.ScopeFile)

	// apply overrides
	if params := flags.Override; params != nil {
		ApplyFlagOverrides(*params, &spec)
		ConfigureSpec(&spec)
	}

	// create provider of resources for scope
	provider := NewProvider(flags, spec.Servers, spec.SyncGateways, spec.Accels, spec.LoadBalancer)

	// update defaults from spec based on provider
	for i, _ := range spec.Servers {
		// set default port services
		if spec.Servers[i].RestPort == "" {
			if provider.GetType() == "dev" {
				spec.Servers[i].RestPort = "9000"
			} else {
				spec.Servers[i].RestPort = "8091"
			}
		}

		if spec.Servers[i].ViewPort == "" {
			if provider.GetType() == "dev" {
				spec.Servers[i].ViewPort = "9500"
			} else {
				spec.Servers[i].ViewPort = "8092"
			}
		}
		if spec.Servers[i].QueryPort == "" {
			if provider.GetType() == "dev" {
				// query port for cluster run is based
				// on which node has n1ql service
				// since default behavior is to put n1ql
				// on highest node then this is default port
				spec.Servers[i].QueryPort = fmt.Sprintf("%d", 9500-int(spec.Servers[i].Count))
			} else {
				spec.Servers[i].QueryPort = "8093"
			}
		}
		if spec.Servers[i].FTSPort == "" {
			if provider.GetType() == "dev" {
				spec.Servers[i].FTSPort = fmt.Sprintf("%d", 9200+i)
			} else {
				spec.Servers[i].FTSPort = "8094"
			}
		}
		if spec.Servers[i].EventingPort == "" {
			if provider.GetType() == "dev" {
				spec.Servers[i].EventingPort = fmt.Sprintf("%d", 9200+i)
			} else {
				spec.Servers[i].EventingPort = "8096"
			}
		}
		if spec.Servers[i].AnalyticsPort == "" {
			if provider.GetType() == "dev" {
				spec.Servers[i].AnalyticsPort = fmt.Sprintf("%d", 9200+i)
			} else {
				spec.Servers[i].AnalyticsPort = "8095"
			}
		}
	}
	var loops = 0
	if *flags.Continue == true {
		loops++ // we've already done first pass
	}

	rest := NewRestClient(spec.Servers, provider, cm)

	return Scope{
		spec,
		cm,
		provider,
		flags,
		"",
		cmap.New(),
		loops,
		rest,
	}
}

func (s *Scope) SetupServer() {
	s.WaitForServers()
	s.InitRestContainer()
	s.InitCli()
	s.InitNodes()
	s.InitCluster()
	s.AddUsers()
	s.AddNodes()
	s.RebalanceClusters()
	s.CreateBuckets()
	s.CreateViews()
}

func (s *Scope) SetupMobile() {
	waitForResources := false

	// Setup Sync Gateways
	if len(s.Spec.SyncGateways) > 0 {
		s.Provider.ProvideSyncGateways(s.Spec.SyncGateways)
		waitForResources = true
	}

	// Setup Accels
	if len(s.Spec.Accels) > 0 {
		s.Provider.ProvideAccels(s.Spec.Accels)
		waitForResources = true
	}

	// Wait for Sync Gateways / Accels to be available
	if waitForResources {
		s.WaitForMobile()
	}

	// If load balancer is defined in scope
	// Add Sync Gateway to the load balancer
	if s.Spec.LoadBalancer.Name != "" {
		s.Provider.ProvideLoadBalancer(s.Spec.LoadBalancer)
	}

	if waitForResources {
		s.WriteHostConfig()
	}
}

// WriteHostConfig writes a json representation of the topology
// that is used by mobile testkit to run functional tests
// against Sync Gateway
func (s *Scope) WriteHostConfig() {
	GenerateMobileHostDefinition(s)
}

func (s *Scope) StartTopologyWatcher() {
	if s.Rest.IsWatching == false {
		go s.Rest.WatchForTopologyChanges()
	}
}

func (s *Scope) Teardown() {
	// descope
	s.DeleteBuckets()
	s.RemoveNodes()
}

func (s *Scope) InitRestContainer() {
	// make sure container used for rest calls exists
	s.Cm.PullImage("appropriate/curl")
}

func (s *Scope) InitCli() {

	// make sure proper couchbase-cli is used for node init
	var version string
	if s.Flags.Version != nil && (*s.Flags.Version != "") {
		version = *s.Flags.Version
	} else {
		version = s.Rest.GetServerVersion()
	}

	s.Version = version[:3]
	// pull cli tag matching version..ie 3.5, 4.1, 4.5
	// :latest is used if no match found
	s.Cm.PullTaggedImage("sequoiatools/couchbase-cli", s.Version)

}

func (s *Scope) WaitForServers() {

	var image = "martin/wait"

	// use martin/wait container to wait for node to listen on port 8091
	waitForServersOp := func(name string, server *ServerSpec, done chan bool) {

		ip := s.Provider.GetHostAddress(name)
		parts := strings.Split(ip, ",")
                prefix := parts[0]
                if prefix == "syncgateway" || prefix == "elasticsearch" {
                        if len(parts) > 1 {
                                ip = parts[1]
			}
		}
		ipPort := strings.Split(ip, ":")
		if len(ipPort) == 1 {
			// use default port
			ip = ip + ":8091"
		}

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

		s.Cm.Run(&task)
		done <- true
	}

	// verify nodes
	s.Spec.ApplyToAllServersAsync(waitForServersOp)
}

func (s *Scope) WaitForMobile() {

	var image = "martin/wait"

	// use martin/wait container to wait for Sync Gateway to listen on port 4984
	waitForSyncGatewaysOp := func(name string, syncGateway *SyncGatewaySpec, done chan bool) {

		ip := s.Provider.GetHostAddress(name)
		ipPort := strings.Split(ip, ":")
		if len(ipPort) == 1 {
			// use default port
			ip = ip + ":4984"
		}

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

		s.Cm.Run(&task)
		done <- true
	}

	// use martin/wait container to wait for Accel to listen on port 4984
	waitForAccelsOp := func(name string, accel *AccelSpec, done chan bool) {

		ip := s.Provider.GetHostAddress(name)
		ipPort := strings.Split(ip, ":")
		if len(ipPort) == 1 {
			// use default port
			ip = ip + ":4985"
		}

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

		s.Cm.Run(&task)
		done <- true
	}

	s.Spec.ApplyToAllSyncGatewayAsync(waitForSyncGatewaysOp)
	s.Spec.ApplyToAllAccelsAsync(waitForAccelsOp)
}

func (s *Scope) GetPath(path, name string) string {

	// set data path, or use default if unset
	dataPath := "/opt/couchbase/var/lib/couchbase/data"

	if s.Provider.GetType() == "dev" {

		devDataPath := fmt.Sprintf("%s/%s", "/tmp/data", name)
		CreateFile(devDataPath, ".dummy")
		dataPath = devDataPath

	} else if path != "" {

		// paths cannot be used for docker/swarm providers
		if s.Provider.GetType() != "docker" && s.Provider.GetType() != "swarm" {
			dataPath = path
		}
	}

	return dataPath
}

func (s *Scope) InitNodes() {

	var image = "sequoiatools/couchbase-cli"

	initNodesOp := func(name string, server *ServerSpec, done chan bool) {
		ip := s.Provider.GetHostAddress(name)
		parts := strings.Split(ip, ",")
		prefix := parts[0]
                if prefix == "syncgateway" || prefix == "elasticsearch" {
			return
		}
		command := []string{"node-init",
			"-c", ip,
			"-u", server.RestUsername,
			"-p", server.RestPassword,
		}

		server.DataPath = s.GetPath(server.DataPath, name)
		command = append(
			command,
			"--node-init-data-path",
			server.DataPath)

		server.IndexPath = s.GetPath(server.IndexPath, name)
		command = append(
			command,
			"--node-init-index-path",
			server.IndexPath)

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

		s.Cm.Run(&task)
		done <- true
	}

	// verify nodes
	s.Spec.ApplyToAllServersAsync(initNodesOp)
}

func (s *Scope) InitCluster() {

	var image = "sequoiatools/couchbase-cli"

	initClusterOp := func(name string, server *ServerSpec) {
		orchestrator := server.Names[0]
		ip := s.Provider.GetHostAddress(orchestrator)
		servicesList := server.NodeServices[name]
		services := strings.Join(servicesList, ",")
		ramQuota := server.Ram
		if ramQuota == "" {
			// use cluster mcdReserved
			memTotal := s.Rest.GetMemReserved(name)
			ramQuota = strconv.Itoa(memTotal)
		}
		if strings.Index(ramQuota, "%") > -1 {
			// use percentage of memtotal
			ramQuota = s.GetPercOfMemTotal(name, server, ramQuota)
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

		// make sure if index services is specified that index ram is set
		if strings.Index(services, "index") > -1 && server.IndexRam == "" {
			q := s.Rest.GetIndexQuota(name)
			server.IndexRam = strconv.Itoa(q)
		}
		if server.IndexRam != "" {
			indexQuota := server.IndexRam
			if strings.Index(indexQuota, "%") > -1 {
				// use percentage of memtotal
				indexQuota := s.GetPercOfMemTotal(name, server, indexQuota)
				server.IndexRam = indexQuota
			}
			command = append(command, "--cluster-index-ramsize", server.IndexRam)
		}
		// make sure if fts services is specified that fts ram is set
		if strings.Index(services, "fts") > -1 && server.FtsRam == "" {
			server.FtsRam = "256"
		}
		if server.FtsRam != "" {
			ftsQuota := server.FtsRam
			if strings.Index(ftsQuota, "%") > -1 {
				// use percentage of memtotal
				ftsQuota := s.GetPercOfMemTotal(name, server, ftsQuota)
				server.FtsRam = ftsQuota
			}
			command = append(command, "--cluster-fts-ramsize", server.FtsRam)
		}

		if server.IndexStorage != "" {
			command = append(command, "--index-storage-setting", server.IndexStorage)
		}
		// make sure if analytics services is specified that analytics ram is set
		if strings.Index(services, "analytics") > -1 && server.AnalyticsRam == "" {
			server.AnalyticsRam = "1024"
		}
		if server.AnalyticsRam != "" {
			analyticsQuota := server.AnalyticsRam
			if strings.Index(analyticsQuota, "%") > -1 {
				// use percentage of memtotal
				analyticsQuota := s.GetPercOfMemTotal(name, server, analyticsQuota)
				server.AnalyticsRam = analyticsQuota
			}
			command = append(command, "--cluster-analytics-ramsize", server.AnalyticsRam)
		}

		// make sure if eventing services is specified that eventing ram is set
		if strings.Index(services, "eventing") > -1 && server.EventingRam == "" {
			server.EventingRam = "256"
		}
		if server.EventingRam != "" {
			eventingQuota := server.EventingRam
			if strings.Index(eventingQuota, "%") > -1 {
				// use percentage of memtotal
				eventingQuota := s.GetPercOfMemTotal(name, server, eventingQuota)
				server.EventingRam = eventingQuota
			}
			command = append(command, "--cluster-eventing-ramsize", server.EventingRam)
		}

		command = cliCommandValidator(s.Version, command)

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
		s.Cm.Run(&task)
		server.NodesActive++

	}

	// apply only to orchestrator
	s.Spec.ApplyToServers(initClusterOp, 0, 1)

}

func (s *Scope) AddUsers() {

	// spock only
	if strings.Compare(s.Version, "5.0") == -1 {
		return
	}

	var image = "sequoiatools/couchbase-cli"

	// add users
	operation := func(name string, server *ServerSpec) {
		orchestrator := server.Names[0]
		ip := s.Provider.GetHostAddress(orchestrator)

		for _, user := range server.RbacSpecs {

			roles := user.Roles
			if roles == "" {
				roles = "admin"
			}

			// auth_domain can override auth_type
			auth_domain := user.AuthDomain
			if auth_domain == "" {
				auth_domain = "builtin"
			}
			command := []string{"user-manage", "-c", ip,
				"-u", server.RestUsername, "-p", server.RestPassword,
				"--rbac-username", user.Name,
				"--rbac-password", user.Password,
				"--roles", roles,
				"--auth-domain", auth_domain,
				"--set",
			}

			desc := "create rbac user " + user.Name
			task := ContainerTask{
				Describe: desc,
				Image:    image,
				Command:  command,
				Async:    false,
			}
			if s.Provider.GetType() == "docker" {
				task.LinksTo = orchestrator
			}

			s.Cm.Run(&task)
		}
	}

	// apply only to orchestrator of each cluster
	s.Spec.ApplyToServers(operation, 0, 1)
}

func (s *Scope) AddNodes() {

	var image = "sequoiatools/couchbase-cli"

	addNodesOp := func(name string, server *ServerSpec) {

		if server.InitNodes <= server.NodesActive {
			return
		}
		orchestrator := server.Names[0]
		orchestratorIp := s.Provider.GetHostAddress(orchestrator)
		ip := s.Provider.GetHostAddress(name)

		parts := strings.Split(ip, ",")
                prefix := parts[0]
                if prefix == "syncgateway" || prefix == "elasticsearch" {
                        return
                }

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
		command = cliCommandValidator(s.Version, command)

		task := ContainerTask{
			Describe: desc,
			Image:    image,
			Command:  command,
			Async:    false,
		}
		if s.Provider.GetType() == "docker" {
			task.LinksTo = orchestrator
		}

		s.Cm.Run(&task)
		server.NodesActive++

	}

	// add nodes
	s.Spec.ApplyToAllServers(addNodesOp)
}

func (s *Scope) RebalanceClusters() {

	var image = "sequoiatools/couchbase-cli"
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

		s.Cm.Run(&task)
	}

	// apply only to orchestrator
	s.Spec.ApplyToServers(operation, 0, 1)

}

func (s *Scope) CreateBuckets() {

	var image = "sequoiatools/couchbase-cli"

	// configure rebalance operation
	operation := func(name string, server *ServerSpec) {

		orchestrator := server.Names[0]
		ip := s.Provider.GetHostAddress(orchestrator)

		for _, bucket := range server.BucketSpecs {
			for _, bucketName := range bucket.Names {
				ramQuota := bucket.Ram
				if strings.Index(ramQuota, "%") > -1 {
					// convert bucket ram to value within context of server ram
					ramQuota = strings.Replace(ramQuota, "%", "", 1)
					ramVal, _ := strconv.Atoi(ramQuota)
					nodeRam, _ := strconv.Atoi(server.Ram)
					ramQuota = strconv.Itoa((nodeRam * ramVal) / 100)
				}
				var replica uint8 = 1
				if bucket.Replica != nil {
					replica = *bucket.Replica
				}
				command := []string{"bucket-create", "-c", ip,
					"-u", server.RestUsername, "-p", server.RestPassword,
					"--bucket", bucketName,
					"--bucket-ramsize", ramQuota,
					"--bucket-type", bucket.Type,
					"--bucket-replica", strconv.Itoa(int(replica)),
					"--enable-flush", "1", "--wait",
				}
				if bucket.Sasl != "" {
					command = append(command, "--password", bucket.Sasl)
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

				s.Cm.Run(&task)
			}
		}
	}

	// apply only to orchestrator
	s.Spec.ApplyToServers(operation, 0, 1)

}

func (s *Scope) GetPercOfMemTotal(name string, server *ServerSpec, quota string) string {
	memTotal := s.ClusterMemTotal(name, server)
	ramQuota := strings.Replace(quota, "%", "", 1)
	ramVal, _ := strconv.Atoi(ramQuota)
	ramQuota = strconv.Itoa((memTotal * ramVal) / 100)
	return ramQuota
}

func (s *Scope) ClusterMemTotal(name string, server *ServerSpec) int {
	mem := s.Rest.GetMemTotal(name)
	if s.Provider.GetType() == "docker" {
		p := s.Provider.(*DockerProvider)
		if p.Opts.Memory > 0 {
			mem = p.Opts.MemoryMB()
		}
	}
	return mem
}

func (s *Scope) CompileCommand(actionCommand string) []string {

	// remove extraneous white space
	re := regexp.MustCompile(`\s+`)
	actionCommand = re.ReplaceAllString(actionCommand, " ")

	// parse template
	actionCommand = ParseTemplate(s, actionCommand)

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

//
// cliCommandValidator checks the cli command for opts that
// could possibly be invalid based on version
//
func cliCommandValidator(version string, command []string) []string {

	if version == "" {
		fmt.Println("version not set")
		return command
	}

	result := []string{}
	vMajor, _ := strconv.ParseFloat(version, 64)

	for i, arg := range command {
		if i == 0 {
			// action
			result = append(result, command[0])
			continue
		}
		// must be an arg
		if strings.Index(arg, "-") != 0 {
			continue
		}

		// >5.0 builds
		if vMajor >= 5.0 {
			// remove -u/-p from cluster_init
			if command[0] == "cluster-init" {
				if arg == "-u" ||
					arg == "-p" {
					continue
				}
			}
			// rename memory_optimized/forestdb to memopt/default, respectively
			if arg == "--index-storage-setting" {
				if len(command) > (i + 1) {
					if command[i+1] == "memory_optimized" {
						command[i+1] = "memopt"
					}
					if command[i+1] == "forestdb" {
						command[i+1] = "default"
					}
				}
			}
		}

		// <4.5 builds
		if vMajor < 4.5 {
			if arg == "--index-storage-setting" ||
				arg == "--cluster-fts-ramsize" {
				continue
			}
		}

		// <4.0 builds
		if vMajor < 4.0 && (arg == "--services" ||
			arg == "--cluster-index-ramsize" ||
			arg == "--node-init-index-path") {
			continue
		}

		// copy arg
		result = append(result, arg)
		// check if arg has value
		if i+1 < len(command) {
			result = append(result, command[i+1])
		}
	}

	return result
}

func (s *Scope) CreateViews() {

	var image = "appropriate/curl"

	operation := func(name string, server *ServerSpec) {

		orchestrator := server.Names[0]
		ip := s.Provider.GetHostAddress(orchestrator)

		// for each bucket name
		for _, bucket := range server.BucketSpecs {
			for _, bucketName := range bucket.Names {

				// add ddocs to bucket
				for _, ddoc := range bucket.DDocSpecs {

					// combine ddoc views
					var ddocDef = DDocToJson(ddoc)

					// compose view create command
					ip = strings.Split(ip, ":")[0]
					viewUrl := fmt.Sprintf("http://%s:%s/%s/_design/%s",
						ip, server.ViewPort, bucketName, ddoc.Name)
					command := []string{"-s", "-X", "PUT",
						"-u", server.RestUsername + ":" + server.RestPassword,
						"-H", "Content-Type:application/json",
						viewUrl,
						"-d", ddocDef,
					}
					desc := "views create" + bucketName
					task := ContainerTask{
						Describe: desc,
						Image:    image,
						Command:  command,
						Async:    false,
					}
					if s.Provider.GetType() == "docker" {
						task.LinksTo = orchestrator
					}
					s.Cm.Run(&task)
				}
			}
		}
	}

	// apply only to orchestrator
	s.Spec.ApplyToServers(operation, 0, 1)

}

func (s *Scope) DeleteBuckets() {

	var image = "sequoiatools/couchbase-cli"

	// configure rebalance operation
	operation := func(name string, server *ServerSpec) {

		orchestrator := server.Names[0]
		ip := s.Provider.GetHostAddress(orchestrator)

		for _, bucket := range server.BucketSpecs {
			for _, bucketName := range bucket.Names {

				command := []string{"bucket-delete", "-c", ip,
					"-u", server.RestUsername, "-p", server.RestPassword,
					"--bucket", bucketName,
				}

				desc := "bucket delete" + bucketName
				task := ContainerTask{
					Describe: desc,
					Image:    image,
					Command:  command,
					Async:    false,
				}
				if s.Provider.GetType() == "docker" {
					task.LinksTo = orchestrator
				}

				s.Cm.Run(&task)
			}
		}
	}

	// apply only to orchestrator
	s.Spec.ApplyToServers(operation, 0, 1)

}

func (s *Scope) RemoveNodes() {

	var image = "sequoiatools/couchbase-cli"

	rmNodesOp := func(name string, server *ServerSpec) {

		orchestrator := server.Names[0]
		orchestratorIp := s.Provider.GetHostAddress(orchestrator)
		ip := s.Provider.GetHostAddress(name)
		
		parts := strings.Split(ip, ",")
                prefix := parts[0]
                if prefix == "syncgateway" || prefix == "elasticsearch" {
                        return
                }

		if name == orchestrator {
			return // not removing self
		}

		command := []string{"rebalance",
			"-c", orchestratorIp,
			"-u", server.RestUsername,
			"-p", server.RestPassword,
			"--server-remove", ip,
		}

		desc := "remove node " + ip
		command = cliCommandValidator(s.Version, command)

		task := ContainerTask{
			Describe: desc,
			Image:    image,
			Command:  command,
			Async:    false,
		}
		if s.Provider.GetType() == "docker" {
			task.LinksTo = orchestrator
		}

		s.Cm.Run(&task)
	}

	// add nodes
	s.Spec.ApplyToAllServers(rmNodesOp)
}

func (s *Scope) GetPlatform() string {
	return *s.Flags.Platform
}

func (s *Scope) SetVarsKV(key, id string) {
	s.Vars.Set(key, id)
}

func (s *Scope) GetVarsKV(key string) (string, bool) {
	if val, ok := s.Vars.Get(key); ok {
		return val.(string), ok
	} else {
		return "", false
	}
}

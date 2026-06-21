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
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"

	cmap "github.com/streamrail/concurrent-map"
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

type Services struct {
	Hostname string
	Services []string
}

func NewScope(flags TestFlags, cm *ContainerManager) Scope {

	// init from yaml or ini
	spec := NewScopeSpec(*flags.ScopeFile)

	// apply overrides
	if params := flags.Override; *params != "" {
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
		if spec.Servers[i].BackupPort == "" {
			if provider.GetType() == "dev" {
				spec.Servers[i].BackupPort = fmt.Sprintf("%d", 9200+i)
			} else {
				spec.Servers[i].BackupPort = "8097"
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
	if !(*s.Flags.Capella) {
		s.WaitForServers()
		s.InitCli()
		s.InitNodes()
		s.InitCluster()
		s.AddUsers()
		s.EnableDiagEvalOnNonLocalHosts()
		s.BypassEncryptionRestrictions()
		s.CreateEncryptionKeys()
		s.EnableEncryptionKey()
		s.EnableOtherEncryptionAtRest()
		s.EnableLogAndConfigEncryption()
		s.EnableClientCertAuth(
			"hybrid",
			"subject.cn",
			"",
			"",
			"/tmp",
		)
		s.AddNodes()
		s.RebalanceClusters()
		/* this setting is no longer needed. Uncomment if it causes problems*/
		//s.ApplyInternalSettings()
		s.CreateBuckets()
	}
	s.getClusteInfo()
	s.InitRestContainer()
	s.CreateScope()
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
	if !*s.Flags.SkipPull {
		s.Cm.PullTaggedImage("sequoiatools/couchbase-cli", s.Version)
	}

}

func (s *Scope) GetCliImage() string {
	// make sure proper couchbase-cli is used
	var version string
	if s.Flags.Version != nil && (*s.Flags.Version != "") {
		version = *s.Flags.Version
	} else {
		version = s.Rest.GetServerVersion()
	}
	s.Version = version[:3]
	return "sequoiatools/couchbase-cli:" + s.Version
}

func (s *Scope) WaitForServers() {

	var image = "martin/wait"

	// use martin/wait container to wait for node to listen on port 8091
	waitForServersOp := func(name string, server *ServerSpec, done chan bool) {

		ip := s.Provider.GetHostAddress(name)

		// Validate that we got a valid IP address
		if ip == "" {
			fmt.Printf("Warning: Empty IP address for server %s, skipping wait operation\n", name)
			done <- true
			return
		}

		parts := strings.Split(ip, ",")
		prefix := parts[0]
		if prefix == "syncgateway" || prefix == "elasticsearch" {
			if len(parts) > 1 {
				ip = parts[1]
			} else {
				// If we have syncgateway/elasticsearch prefix but no second part, skip
				fmt.Printf("Warning: Invalid IP format for %s (expected format: syncgateway,ip or elasticsearch,ip), skipping wait operation\n", name)
				done <- true
				return
			}
		}

		// Validate IP after potential modification
		if ip == "" {
			fmt.Printf("Warning: Empty IP address after processing for server %s, skipping wait operation\n", name)
			done <- true
			return
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

		// Validate that we got a valid IP address
		if ip == "" {
			fmt.Printf("Warning: Empty IP address for sync gateway %s, skipping wait operation\n", name)
			done <- true
			return
		}

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

		// Validate that we got a valid IP address
		if ip == "" {
			fmt.Printf("Warning: Empty IP address for accel %s, skipping wait operation\n", name)
			done <- true
			return
		}

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
	var image = s.GetCliImage()
	initNodesOp := func(name string, server *ServerSpec, done chan bool) {
		ip := s.Provider.GetHostAddress(name)
		parts := strings.Split(ip, ",")
		prefix := parts[0]
		if prefix == "syncgateway" || prefix == "elasticsearch" {
			fmt.Printf("Skipping node-init for %s (type: %s) - not a Couchbase Server node\n", name, prefix)
			done <- true
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

		server.AnalyticsPath = s.GetPath(server.AnalyticsPath, name)
		partition := strings.Split(server.AnalyticsPath, ",")
		for _, path := range partition {
			command = append(
				command,
				"--node-init-analytics-path",
				path)
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

		s.Cm.Run(&task)
		done <- true
	}

	// verify nodes
	s.Spec.ApplyToAllServersAsync(initNodesOp)
}

func (s *Scope) InitCluster() {
	var image = s.GetCliImage()
	initClusterOp := func(name string, server *ServerSpec) {
		orchestrator := server.Names[0]
		ip := s.Provider.GetHostAddress(orchestrator)
		servicesList := server.NodeServices[name]
		// translate internal "arbiter" service name to the couchbase-cli
		// "manager-only" service identifier just before invocation.
		cliServices := make([]string, len(servicesList))
		for idx, svc := range servicesList {
			if svc == "arbiter" {
				cliServices[idx] = "manager-only"
			} else {
				cliServices[idx] = svc
			}
		}
		services := strings.Join(cliServices, ",")
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
	var image = s.GetCliImage()

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

func (s *Scope) CreateEncryptionKeys() {
	operation := func(name string, server *ServerSpec) {
		orchestrator := server.Names[0]
		if !encryptionEnabledOnServer(server) {
			fmt.Printf("[CreateEncryptionKeys] %s: skipped (no encryption usage configured)\n", name)
			return
		}

		// Build the usage list from the server spec. Mirrors the CLI flag
		// translation that encryptionUsageFlags used to do, but in the REST
		// API's vocabulary.
		usage := []string{}
		if server.EnableOtherEncryptionAtRest {
			usage = append(usage, "KEK-encryption", "other-encryption")
		}
		if server.EnableConfigEncryptionAtRest {
			usage = append(usage, "config-encryption")
		}
		if server.EnableAuditEncryptionAtRest {
			usage = append(usage, "audit-encryption")
		}
		if server.EnableLogEncryptionAtRest {
			usage = append(usage, "log-encryption")
		}
		for _, bucket := range server.BucketSpecs {
			if bucket.EnableEncryptionAtRest {
				usage = append(usage, "bucket-encryption")
				break
			}
		}
		usage = uniqueStrings(usage)

		// Mirror the UI's create-key payload when auto-rotation is enabled:
		// autoRotation=true requires rotationIntervalInDays and a
		// nextRotationTime in the ".000Z" millisecond RFC3339 form ns_server
		// accepts.
		nextRotation := time.Now().UTC().Add(1 * time.Hour).Format("2006-01-02T15:04:05.000Z")
		payload := map[string]interface{}{
			"name":  "universal_key",
			"type":  "cb-server-managed-aes-key-256",
			"usage": usage,
			"data": map[string]interface{}{
				"autoRotation":           true,
				"encryptWith":            "nodeSecretManager",
				"rotationIntervalInDays": 1,
				"nextRotationTime":       nextRotation,
				"canBeCached":            true,
			},
		}
		payloadBytes, err := json.Marshal(payload)
		if err != nil {
			fmt.Printf("[CreateEncryptionKeys] %s: marshal error: %v\n", name, err)
			return
		}

		fmt.Printf("[CreateEncryptionKeys] %s: creating universal_key with usage=%v\n", name, usage)
		if err := s.Rest.CreateEncryptionKey(orchestrator, payloadBytes); err != nil {
			fmt.Printf("[CreateEncryptionKeys] ERROR %s: %v\n", name, err)
		} else {
			fmt.Printf("[CreateEncryptionKeys] %s: success\n", name)
		}
	}

	s.Spec.ApplyToServers(operation, 0, 1)
}
func (s *Scope) AddNodes() {
	var image = s.GetCliImage()
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
		// translate internal "arbiter" service name to the couchbase-cli
		// "manager-only" service identifier just before invocation.
		cliServices := make([]string, len(servicesList))
		for idx, svc := range servicesList {
			if svc == "arbiter" {
				cliServices[idx] = "manager-only"
			} else {
				cliServices[idx] = svc
			}
		}
		services := strings.Join(cliServices, ",")
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

func (s *Scope) CreateClientAuthFile(state, pathVal, prefix, delimiter, outputDir string) (string, error) {

	config := map[string]interface{}{
		"state": state,
		"prefixes": []map[string]string{
			{
				"path":      pathVal,
				"prefix":    prefix,
				"delimiter": delimiter,
			},
		},
	}

	data, err := json.MarshalIndent(config, "", "  ")
	if err != nil {
		return "", err
	}

	if err := os.MkdirAll(outputDir, 0755); err != nil {
		return "", err
	}

	filePath := filepath.Join(outputDir, "client-auth-settings.json")
	if err := os.WriteFile(filePath, data, 0644); err != nil {
		return "", err
	}
	return filePath, nil
}

func (s *Scope) EnableClientCertAuth(state, pathVal, prefix, delimiter, outputDir string) error {
	var image = s.GetCliImage()

	operation := func(name string, server *ServerSpec) {
		orchestrator := server.Names[0]
		filePath, err := s.CreateClientAuthFile(state, pathVal, prefix, delimiter, "/tmp")
		if err != nil {
			fmt.Printf("Error creating client auth file: %v\n", err)
			return
		}
		ip := s.Provider.GetHostAddress(orchestrator)

		command := []string{
			"ssl-manage",
			"-c", ip,
			"-u", server.RestUsername,
			"-p", server.RestPassword,
			"--set-client-auth", "/tmp/client-auth-settings.json",
		}

		command = cliCommandValidator(s.Version, command)
		desc := "enable client certificate handling " + name
		task := ContainerTask{
			Describe: desc,
			Image:    image,
			Command:  command,
			Async:    false,
			Volumes:  []string{filePath + ":/tmp/client-auth-settings.json"},
		}

		s.Cm.Run(&task)
	}

	s.Spec.ApplyToServers(operation, 0, 1)
	return nil
}

func (s *Scope) enableEncryptionAtRest(target, descTarget string, shouldEnable func(*ServerSpec) bool) {
	var image = s.GetCliImage()
	operation := func(name string, server *ServerSpec) {
		if shouldEnable != nil && !shouldEnable(server) {
			return
		}

		orchestrator := server.Names[0]
		ip := s.Provider.GetHostAddress(orchestrator)

		command := []string{"setting-encryption",
			"-c", ip,
			"-u", server.RestUsername,
			"-p", server.RestPassword,
			"--target", target,
			"--type", "key",
			"--key", "0",
		}
		if server.DekRotateEvery != "" {
			command = append(command, "--dek-rotate-every", server.DekRotateEvery)
		}
		command = append(command, "--set")

		desc := "enable " + descTarget + " encryption " + name
		command = cliCommandValidator(s.Version, command)

		task := ContainerTask{
			Describe: desc,
			Image:    image,
			Command:  command,
			Async:    false,
		}
		fmt.Printf("Enabling %s encryption: %s\n", descTarget, name)
		fmt.Printf("Command: %v\n", command)
		fmt.Printf("Task Description: %s\n", desc)

		s.Cm.Run(&task)
	}

	s.Spec.ApplyToServers(operation, 0, 1)
}

func (s *Scope) EnableConfigEncryptionAtRest() {
	s.enableEncryptionAtRest("config", "config", func(server *ServerSpec) bool {
		return server.EnableConfigEncryptionAtRest
	})
}

func (s *Scope) EnableAuditEncryptionAtRest() {
	s.enableEncryptionAtRest("audit", "audit", func(server *ServerSpec) bool {
		return server.EnableAuditEncryptionAtRest
	})
}

func (s *Scope) EnableLogEncryptionAtRest() {
	s.enableEncryptionAtRest("log", "log", func(server *ServerSpec) bool {
		return server.EnableLogEncryptionAtRest
	})
}

func (s *Scope) EnableLogAndConfigEncryption() {
	s.EnableConfigEncryptionAtRest()
	s.EnableAuditEncryptionAtRest()
	s.EnableLogEncryptionAtRest()
}

// selectEncryptionKey fetches the encryption keys on the orchestrator and
// returns the universal_key (or the first key if no universal_key is present).
func (s *Scope) selectEncryptionKey(name string, server *ServerSpec) (EncryptionKey, bool) {
	orchestrator := server.Names[0]
	keys, err := s.Rest.GetEncryptionKeys(orchestrator)
	if err != nil {
		fmt.Printf("Error fetching encryption keys for %s: %v\n", name, err)
		return EncryptionKey{}, false
	}
	if len(keys) == 0 {
		fmt.Printf("No encryption keys found for %s\n", name)
		return EncryptionKey{}, false
	}

	selected := keys[0]
	for _, key := range keys {
		if key.Name == "universal_key" {
			selected = key
			break
		}
	}
	if selected.ID == "" {
		fmt.Printf("No usable encryption key id found for %s\n", name)
		return EncryptionKey{}, false
	}
	return selected, true
}

// EnableEncryptionKey fetches the universal_key id and PUTs it back with the
// usages configured on the server so the key becomes usable for the requested
// encryption targets (config/audit/log/bucket/other).
func (s *Scope) EnableEncryptionKey() {
	operation := func(name string, server *ServerSpec) {
		if !cliVersionAtLeast(s.Version, 8.1) {
			fmt.Printf("Skipping encryption key enable for %s: cli version %s does not support it\n", name, s.Version)
			return
		}
		if !encryptionEnabledOnServer(server) {
			return
		}

		selected, ok := s.selectEncryptionKey(name, server)
		if !ok {
			return
		}

		usage := append([]string{}, selected.Usage...)
		if server.EnableOtherEncryptionAtRest {
			usage = append(usage, "KEK-encryption", "other-encryption")
		}
		if server.EnableConfigEncryptionAtRest {
			usage = append(usage, "config-encryption")
		}
		if server.EnableAuditEncryptionAtRest {
			usage = append(usage, "audit-encryption")
		}
		if server.EnableLogEncryptionAtRest {
			usage = append(usage, "log-encryption")
		}
		for _, bucket := range server.BucketSpecs {
			if bucket.EnableEncryptionAtRest {
				usage = append(usage, "bucket-encryption")
				break
			}
		}

		// The GET response includes ns_server-managed read-only fields under
		// `data` (notably `keys` — the actual key material — plus things
		// like creation/rotation history). Echoing those back triggers
		// `{"errors":{"data":{"keys":"read only"}}}`. Only forward the
		// caller-writable subset that ns_server's PUT validator accepts.
		writableDataKeys := []string{
			"autoRotation",
			"encryptWith",
			"rotationIntervalInDays",
			"nextRotationTime",
			"canBeCached",
		}
		data := map[string]interface{}{}
		for _, k := range writableDataKeys {
			if v, ok := selected.Data[k]; ok {
				data[k] = v
			}
		}
		// Fill in defaults if any required writable fields were missing.
		if _, ok := data["autoRotation"]; !ok {
			data["autoRotation"] = true
		}
		if _, ok := data["encryptWith"]; !ok {
			data["encryptWith"] = "nodeSecretManager"
		}
		if _, ok := data["rotationIntervalInDays"]; !ok {
			data["rotationIntervalInDays"] = 1
		}
		if _, ok := data["nextRotationTime"]; !ok {
			data["nextRotationTime"] = time.Now().UTC().Add(1 * time.Hour).Format(time.RFC3339Nano)
		}
		if _, ok := data["canBeCached"]; !ok {
			data["canBeCached"] = true
		}

		payload := map[string]interface{}{
			"name":  selected.Name,
			"type":  selected.Type,
			"usage": uniqueStrings(usage),
			"data":  data,
		}
		if payload["type"] == "" {
			payload["type"] = "cb-server-managed-aes-key-256"
		}
		payloadBytes, err := json.Marshal(payload)
		if err != nil {
			fmt.Printf("Error creating encryption key usage payload for %s: %v\n", name, err)
			return
		}

		orchestrator := server.Names[0]
		fmt.Printf("[EnableEncryptionKey] %s: PUT key %s (id=%s) usage=%v\n",
			name, selected.Name, selected.ID, payload["usage"])
		if err := s.Rest.PutEncryptionKey(orchestrator, selected.ID, payloadBytes); err != nil {
			fmt.Printf("[EnableEncryptionKey] ERROR %s: %v\n", name, err)
		} else {
			fmt.Printf("[EnableEncryptionKey] %s: success\n", name)
		}
	}

	s.Spec.ApplyToServers(operation, 0, 1)
}

func (s *Scope) EnableOtherEncryptionAtRest() {
	operation := func(name string, server *ServerSpec) {
		if !server.EnableOtherEncryptionAtRest {
			fmt.Printf("[EnableOtherEncryptionAtRest] %s: skipped (server.EnableOtherEncryptionAtRest=false)\n", name)
			return
		}
		if !cliVersionAtLeast(s.Version, 8.1) {
			fmt.Printf("[EnableOtherEncryptionAtRest] %s: skipped (cli version %s < 8.1)\n", name, s.Version)
			return
		}

		selected, ok := s.selectEncryptionKey(name, server)
		if !ok {
			fmt.Printf("[EnableOtherEncryptionAtRest] %s: skipped (no encryption key found)\n", name)
			return
		}

		// ns_server's /settings/security/encryptionAtRest/other endpoint
		// requires encryptionKeyId to be an integer; EncryptionKey.ID is
		// captured as a string from the GET response, so coerce it back
		// to a number when it is numeric (which it always is for
		// server-managed keys today).
		var keyIDVal interface{} = selected.ID
		if n, err := strconv.Atoi(selected.ID); err == nil {
			keyIDVal = n
		}

		otherPayload := map[string]interface{}{
			"encryptionMethod":    "encryptionKey",
			"encryptionKeyId":     keyIDVal,
			"dekLifetime":         31536000,
			"dekRotationInterval": 2592000,
		}
		if server.DekLifetime != "" {
			otherPayload["dekLifetime"] = server.DekLifetime
		}
		if server.DekRotateEvery != "" {
			otherPayload["dekRotationInterval"] = server.DekRotateEvery
		}
		otherPayloadBytes, err := json.Marshal(otherPayload)
		if err != nil {
			fmt.Printf("[EnableOtherEncryptionAtRest] %s: marshal error: %v\n", name, err)
			return
		}

		orchestrator := server.Names[0]
		fmt.Printf("[EnableOtherEncryptionAtRest] %s: enabling with key id=%v\n", name, keyIDVal)
		if err := s.Rest.ConfigureOtherEncryptionAtRest(orchestrator, otherPayloadBytes); err != nil {
			fmt.Printf("[EnableOtherEncryptionAtRest] ERROR %s: %v\n", name, err)
		} else {
			fmt.Printf("[EnableOtherEncryptionAtRest] %s: success\n", name)
		}
	}

	s.Spec.ApplyToServers(operation, 0, 1)
}

func encryptionEnabledOnServer(server *ServerSpec) bool {
	if server.EnableOtherEncryptionAtRest ||
		server.EnableConfigEncryptionAtRest ||
		server.EnableAuditEncryptionAtRest ||
		server.EnableLogEncryptionAtRest {
		return true
	}
	for _, bucket := range server.BucketSpecs {
		if bucket.EnableEncryptionAtRest {
			return true
		}
	}
	return false
}

func cliVersionAtLeast(version string, min float64) bool {
	if version == "" {
		return false
	}

	v, err := strconv.ParseFloat(version, 64)
	if err != nil {
		return false
	}
	return v >= min
}

func uniqueStrings(values []string) []string {
	seen := map[string]struct{}{}
	result := make([]string, 0, len(values))
	for _, value := range values {
		if value == "" {
			continue
		}
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	return result
}

func (s *Scope) RebalanceClusters() {
	var image = s.GetCliImage()
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

func (s *Scope) ApplyInternalSettings() {
	var image = "appropriate/curl"

	operation := func(name string, server *ServerSpec) {

		orchestrator := server.Names[0]
		ip := s.Provider.GetHostAddress(orchestrator)
		ip = strings.Split(ip, ":")[0]
		internalSettingsUrl := fmt.Sprintf("http://%s:%s/internalSettings",
			ip, server.RestPort)
		command := []string{"-s", "-X", "POST",
			"-u", server.RestUsername + ":" + server.RestPassword,
			internalSettingsUrl,
			"-d", "magmaMinMemoryQuota=256",
		}
		desc := "Setting magmaMinMemoryQuota=256"
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

func (s *Scope) EnableDiagEvalOnNonLocalHosts() {
	operation := func(name string, server *ServerSpec) {
		if !server.EnableDiagEvalOnNonLocalHosts {
			return
		}

		s.execDiagEvalInNode(server, "ns_config:set(allow_nonlocal_eval, true).",
			"Enable diag/eval on non-local hosts")
	}

	s.Spec.ApplyToServers(operation, 0, 1)
}

func (s *Scope) BypassEncryptionRestrictions() {
	var image = "appropriate/curl"

	operation := func(name string, server *ServerSpec) {
		if !server.BypassEncryptionRestrictions {
			return
		}

		orchestrator := server.Names[0]
		ip := s.Provider.GetHostAddress(orchestrator)
		ip = strings.Split(ip, ":")[0]
		diagEvalUrl := fmt.Sprintf("http://%s:%s/diag/eval", ip, server.RestPort)
		command := []string{"-s", "-X", "POST",
			"-u", server.RestUsername + ":" + server.RestPassword,
			diagEvalUrl,
			"-d", "ns_config:set(test_bypass_encr_cfg_restrictions, true).",
		}
		desc := "Bypass encryption restrictions"
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

	s.Spec.ApplyToServers(operation, 0, 1)
}

func (s *Scope) execDiagEvalInNode(server *ServerSpec, expr, desc string) {
	orchestrator := server.Names[0]
	containerID, ok := s.nodeContainerID(orchestrator)
	if !ok || containerID == "" {
		fmt.Printf("Skipping %s for %s: container ID unavailable\n", desc, orchestrator)
		return
	}

	diagEvalUrl := fmt.Sprintf("http://127.0.0.1:%s/diag/eval", server.RestPort)
	command := []string{"curl", "-s", "-X", "POST",
		"-u", server.RestUsername + ":" + server.RestPassword,
		diagEvalUrl,
		"-d", expr,
	}
	fmt.Printf("%s via exec on %s\n", desc, orchestrator)
	if err := s.Cm.ExecContainer(containerID, command, false); err != nil {
		fmt.Printf("Error running %s on %s: %v\n", desc, orchestrator, err)
	}
}

func (s *Scope) nodeContainerID(name string) (string, bool) {
	switch provider := s.Provider.(type) {
	case *DockerProvider:
		id, ok := provider.ActiveContainers[name]
		return id, ok
	case *SwarmProvider:
		id, ok := provider.ActiveContainers[name]
		return id, ok
	default:
		return "", false
	}
}

func (s *Scope) CreateBuckets() {
	var image = s.GetCliImage()

	if s.Spec.Servers[0].NumberOfBuckets != "" {
		s.Rest.updateNumberOfBucktes(s.Spec.Servers[0].NumberOfBuckets)
	}

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
				if bucket.Eviction != "" {
					command = append(command, "--bucket-eviction-policy", bucket.Eviction)
				}
				if bucket.Compression != "" {
					command = append(command, "--compression-mode", bucket.Compression)
				}
				if bucket.TTL != "" {
					command = append(command, "--max-ttl", bucket.TTL)
				}
				if bucket.Storage != "" {
					command = append(command, "--storage-backend", bucket.Storage)
				}
				if bucket.Durability != "" {
					command = append(command, "--durability-min-level", bucket.Durability)
				}
				if bucket.HistoryRetentionBytes != "" {
					command = append(command, "--history-retention-bytes", bucket.HistoryRetentionBytes)
				}
				if bucket.HistoryRetentionSeconds != "" {
					command = append(command, "--history-retention-seconds", bucket.HistoryRetentionSeconds)
				}
				if bucket.EnableHistoryRetentionByDefault != "" {
					command = append(command, "--enable-history-retention-by-default", bucket.EnableHistoryRetentionByDefault)
				}
				if bucket.Rank != "" {
					command = append(command, "--rank", bucket.Rank)
				}
				if bucket.ConflictResolution != "" {
					command = append(command, "--conflict-resolution", bucket.ConflictResolution)
				}
				if bucket.Vbuckets != "" {
					command = append(command, "--num-vbuckets", bucket.Vbuckets)
				}
				if bucket.EnableEncryptionAtRest {
					command = append(command, "--encryption-key", "0")
					if bucket.DekRotateEvery != "" {
						command = append(command, "--dek-rotate-every", bucket.DekRotateEvery)
					}
					if bucket.DekLifetime != "" {
						command = append(command, "--dek-lifetime", bucket.DekLifetime)
					}
				}
				if bucket.EnableContinuousBackup {
					command = append(command, "--continuous-backup-enabled", "1")
					if bucket.ContinuousBackupInterval != "" {
						command = append(command, "--continuous-backup-interval", bucket.ContinuousBackupInterval)
					}
					if bucket.ContinuousBackupLocation != "" {
						command = append(command, "--continuous-backup-location", bucket.ContinuousBackupLocation)
					}
					if bucket.ContinuousBackupRetentionPeriod != 0 {
						command = append(command, "--continuous-backup-retention-period",
							strconv.FormatUint(uint64(bucket.ContinuousBackupRetentionPeriod), 10))
					}
				}
				if bucket.BucketThrottleReserved > 0 {
					command = append(command, "--throttle-reserved", strconv.FormatUint(bucket.BucketThrottleReserved, 10))
				}
				if bucket.BucketThrottleHardLimit > 0 {
					command = append(command, "--throttle-hard-limit", strconv.FormatUint(bucket.BucketThrottleHardLimit, 10))
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

func (s *Scope) CreateScope() {
	for _, bucket := range s.Spec.Buckets {
		//fmt.Print(bucket)
		for _, scopes := range bucket.BucketScopeSpec {
			//	fmt.Print(scopes)
			s.Rest.createScope(bucket.Name, scopes.Name)
			if scopes.Collections != "" {
				for _, collName := range CommaStrToList(scopes.Collections) {
					s.Rest.createCollections(bucket.Name, scopes.Name, collName)
				}
			}
		}
	}
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

// cliCommandValidator checks the cli command for opts that
// could possibly be invalid based on version
func cliCommandValidator(version string, command []string) []string {

	if version == "" {
		fmt.Println("version not set")
		return command
	}

	result := []string{}
	vMajor, _ := strconv.ParseFloat(version, 64)

	result = append(result, command[0])

	for i := 1; i < len(command); i++ {
		arg := command[i]
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
		if i+1 < len(command) && strings.Index(command[i+1], "-") != 0 {
			result = append(result, command[i+1])
			i++
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
	var image = s.GetCliImage()
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
	var image = s.GetCliImage()
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

func (s *Scope) getClusteInfo() {
	cluster := s.Rest.GetClusterInfo()
	serviceMap := make(map[string][]string)
	for i := 0; i < len(cluster.Nodes); i++ {
		host := cluster.Nodes[i].Hostname
		// Arbiter (serviceless) nodes may report no services.
		if len(cluster.Nodes[i].Services) == 0 {
			serviceMap["arbiter"] = append(serviceMap["arbiter"], host)
			continue
		}
		service := cluster.Nodes[i].Services[0]
		serviceMap[service] = append(serviceMap[service], host)
	}
	fmt.Println("########## Cluster config ##################")
	for key, value := range serviceMap {
		fmt.Println("###### ", key, ":", len(value), "===== >", value, " ###########")
	}
}

// StartPeriodicClusterInfo starts a goroutine that prints cluster info every 2 hours
func (s *Scope) StartPeriodicClusterInfo() {
	go func() {
		ticker := time.NewTicker(2 * time.Hour)
		defer ticker.Stop()

		for {
			select {
			case <-ticker.C:
				fmt.Println("########## Periodic Cluster Info (Every 2 Hours) ##################")
				s.getClusteInfo()
				fmt.Println("########## End Periodic Cluster Info ##################")
			}
		}
	}()
}

func (s *Scope) ConfigSyncGateway() {
	var image = "sequoiatools/sgw-config"

	// configure sync gateway
	operation := func(name string, ssh_user string, ssh_pwd string, serverNames []string, bucketName string, bucketUser string, bucketUserPwd string, sgws *[]SyncGatewaySpec) {

		cbs := []string{}
		for _, sn := range serverNames {
			ip := s.Provider.GetHostAddress(sn)
			if ip == "" {
				fmt.Printf("Warning: Empty IP address for server %s, skipping sync gateway config\n", sn)
				return
			}
			cbs = append(cbs, ip)
		}
		cbsIps := strings.Join(cbs, ",")

		sgwIp := s.Provider.GetHostAddress(name)
		if sgwIp == "" {
			fmt.Printf("Warning: Empty IP address for sync gateway %s, skipping sync gateway config\n", name)
			return
		}

		command := []string{"MOBILE_TESTKIT_BRANCH=sequoia/sgw-component-testing",
			"SSH_USER=" + ssh_user,
			"SSH_PWD=" + ssh_pwd,
			"CBS_HOSTS=" + cbsIps,
			"SGW_HOSTS=" + sgwIp,
			"BUCKET_NAME=" + bucketName,
			"BUCKET_USER=" + bucketUser,
			"BUCKET_USER_PASSWORD=" + bucketUserPwd,
		}

		desc := "config sync gateway"
		task := ContainerTask{
			Describe: desc,
			Image:    image,
			Command:  command,
			Async:    false,
		}
		s.Cm.Run(&task)
	}

	// apply only to orchestrator
	s.Spec.ApplyToAllSyncGateway(operation)

}

func (s *Scope) enableDpIfReq() {
	var image = s.GetCliImage()
	// configure dp enable operation for bucket type magma
	operation := func(name string, server *ServerSpec) {
		for _, bucket := range server.BucketSpecs {
			if bucket.Storage == "magma" {
				orchestrator := server.Names[0]
				ip := s.Provider.GetHostAddress(orchestrator)
				command := []string{"enable-developer-preview",
					"-c", ip,
					"-u", server.RestUsername,
					"-p", server.RestPassword,
					"--enable",
				}

				desc := "enable dp " + ip
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
			} else {
				return
			}
		}
	}
	// apply only to orchestrator
	s.Spec.ApplyToServers(operation, 0, 1)
}

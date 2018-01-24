package sequoia

/* Template.go
 *
 * Template Resolver methods
 */

import (
	"bytes"
	"fmt"
	"reflect"
	"strconv"
	"strings"
	"text/template"
)

type TemplateResolver struct {
	Scope *Scope
}

func ParseTemplate(s *Scope, command string) string {

	tResolv := TemplateResolver{s}

	netFunc := template.FuncMap{
		"net":               tResolv.Address,
		"bucket":            tResolv.BucketName,
		"auth_user":         tResolv.AuthUser,
		"noport":            tResolv.NoPort,
		"json":              tResolv.ToJson,
		"to_double_quote":   tResolv.ToDoubleQuotes,
		"wrap_single_quote": tResolv.WrapSingleQuote,
		"ftoint":            tResolv.FloatToInt,
		"strtoint":          tResolv.StrToInt,
		"last":              tResolv.LastItem,
		"contains":          tResolv.Contains,
		"excludes":          tResolv.Excludes,
		"tolist":            tResolv.ToList,
		"strlist":           tResolv.StrList,
		"mkrange":           tResolv.MkRange,
		"to_ip":             tResolv.ToIp,
		"active":            tResolv.ActiveFilter,
	}
	tmpl, err := template.New("t").Funcs(netFunc).Parse(command)
	logerr(err)

	out := new(bytes.Buffer)
	err = tmpl.Execute(out, &tResolv)
	logerr(err)

	return fmt.Sprintf("%s", out)
}

func (t *TemplateResolver) Version() float64 {
	val, _ := strconv.ParseFloat(t.Scope.Version, 64)
	return val
}

func (t *TemplateResolver) DoOnce() bool {
	return t.Scope.Loops == 0
}

func (t *TemplateResolver) EvenCount() bool {
	return (t.Scope.Loops % 2) == 0
}

func (t *TemplateResolver) OddCount() bool {
	return !t.EvenCount()
}

func (t *TemplateResolver) Loop() int {
	return t.Scope.Loops
}

// apply scope scale factor to the value
func (t *TemplateResolver) Scale(val int) string {
	scale := *t.Scope.Flags.Scale
	if scale == 0 {
		scale++
	}
	return strconv.Itoa(val * scale)
}

// resolve nodes with specified service, ie..
// .Nodes | .Service `n1ql` | net 0
func (t *TemplateResolver) Service(service string, servers []ServerSpec) []ServerSpec {

	serviceNodes := []ServerSpec{}
	matchIdx := 0
	for _, spec := range servers {
		added := false
		for _, name := range spec.Names {
			ok := t.Scope.Rest.NodeHasService(service, name)
			if ok == true {
				if added == false {
					serviceNodes = append(serviceNodes, ServerSpec{Names: []string{name}})
					added = true
				} else {
					serviceNodes[matchIdx].Names = append(serviceNodes[matchIdx].Names, name)
				}
			}
		}
		if added == true {
			matchIdx++
		}
	}

	if len(serviceNodes) == 0 {
		// try from provisioning stack
		// it may be that server was removed from cluster
		for _, spec := range servers {
			for name, services := range spec.NodeServices {
				for _, nodeService := range services {
					if nodeService == service {
						serviceNodes = append(serviceNodes, ServerSpec{Names: []string{name}})
					}
				}
			}
		}
	}
	return serviceNodes
}

func (t *TemplateResolver) Nodes() []ServerSpec {
	return t.Scope.Spec.Servers
}

func (t *TemplateResolver) Cluster(index int, servers []ServerSpec) []ServerSpec {
	return []ServerSpec{servers[index]}
}

// Shortcut: .Nodes | .Cluster 0
func (t *TemplateResolver) ClusterNodes() []ServerSpec {
	return t.Cluster(0, t.Nodes())
}

// Retreive just hostnames from ServerSpec object
func (t *TemplateResolver) NodeNames(servers []ServerSpec) []string {
	names := []string{}
	for _, spec := range servers {
		for _, n := range spec.Names {
			names = append(names, n)
		}
	}
	return names
}

// Retreive just addresses from ServerSpec object
func (t *TemplateResolver) NodeAddresses(servers []ServerSpec) []string {

	ips := []string{}
	names := t.NodeNames(servers)
	for _, name := range names {
		ip := t.Scope.Provider.GetHostAddress(name)
		ips = append(ips, ip)
	}
	return ips
}

func (t *TemplateResolver) ToIp(name string) string {
	return t.Scope.Provider.GetHostAddress(name)
}

// Shortcut: .ClusterNodes | net 0
func (t *TemplateResolver) Orchestrator() string {
	nodes := t.ClusterNodes()
	name := nodes[0].Names[0]
	val := t.Scope.Provider.GetHostAddress(name)
	return val
}

// Shortcut: .ClusterNodes | .Service `n1ql` | net 0
func (t *TemplateResolver) QueryNode() string {
	nodes := t.ClusterNodes()
	serviceNodes := t.Service("n1ql", nodes)
	return t.Address(0, serviceNodes)
}

// Shortcut: {{.ClusterNodes | .Attr `rest_port`}}
func (t *TemplateResolver) RestPort() string {
	nodes := t.ClusterNodes()
	return t.Attr("rest_port", nodes)
}

// Shortcut: {{.ClusterNodes | .Attr `query_port`}}
func (t *TemplateResolver) QueryPort() string {
	nodes := t.ClusterNodes()
	return t.Attr("query_port", nodes)
}

// Shortcut: {{.ClusterNodes | .Attr `view_port`}}
func (t *TemplateResolver) ViewPort() string {
	nodes := t.ClusterNodes()
	return t.Attr("view_port", nodes)
}

// Shortcut: {{.ClusterNodes | .Attr `fts_port`}}
func (t *TemplateResolver) FTSPort() string {
	nodes := t.ClusterNodes()
	return t.Attr("fts_port", nodes)
}

// Shortcut: {{.ClusterNodes | .Attr `eventing_port`}}
func (t *TemplateResolver) EventingPort() string {
	nodes := t.ClusterNodes()
	return t.Attr("eventing_port", nodes)
}

// Shortcut: {{.ClusterNodes | .Attr `analytics_port`}}
func (t *TemplateResolver) AnalyticsPort() string {
	nodes := t.ClusterNodes()
	return t.Attr("analytics_port", nodes)
}

// Shortcut: {{.QueryNode | noport}}:{{.QueryPort}}
func (t *TemplateResolver) QueryNodePort() string {
	return fmt.Sprintf("%s:%s", t.NoPort(t.QueryNode()), t.QueryPort())
}

func (t *TemplateResolver) NthQueryNode(n int) string {
	nodes := t.ClusterNodes()
	serviceNodes := t.Service("n1ql", nodes)
	return t.Address(n, serviceNodes)
}

// Shortcut: .ClusterNodes | .Service `kv` | net 0
func (t *TemplateResolver) DataNode() string {
	nodes := t.ClusterNodes()
	serviceNodes := t.Service("kv", nodes)
	return t.Address(0, serviceNodes)
}

// Shortcut: .ClusterNodes | .Service `kv` | net N
func (t *TemplateResolver) NthDataNode(n int) string {
	nodes := t.ClusterNodes()
	version, _ := strconv.ParseFloat(t.Scope.Version, 64)
	if version > 4.0 {
		nodes = t.Service("kv", nodes)
	} // otherwise everything is data

	return t.Address(n, nodes)
}

// Shortcut: .ClusterNodes | .Service `index` | net 0
func (t *TemplateResolver) IndexNode() string {
	nodes := t.ClusterNodes()
	serviceNodes := t.Service("index", nodes)
	return t.Address(0, serviceNodes)
}

// Shortcut: .ClusterNodes | .Service `index` | net N
func (t *TemplateResolver) NthIndexNode(n int) string {
	nodes := t.ClusterNodes()
	serviceNodes := t.Service("index", nodes)
	return t.Address(n, serviceNodes)
}

// Shortcut: .ClusterNodes | .Service `index` | net -1
func (t *TemplateResolver) LastIndexNode() string {
	nodes := t.ClusterNodes()
	serviceNodes := t.Service("index", nodes)
	addr := t.Address(len(serviceNodes[0].Names)-1, serviceNodes)
	return addr
}

// Shortcut: {{.IndexNode | noport}}:{{.RestPort}}
func (t *TemplateResolver) IndexNodePort() string {
	return fmt.Sprintf("%s:%s", t.NoPort(t.IndexNode()), t.RestPort())
}

// Shortcut: .FTSNode | .Service `fts` | net 0
func (t *TemplateResolver) FTSNode() string {
	nodes := t.ClusterNodes()
	serviceNodes := t.Service("fts", nodes)
	return t.Address(0, serviceNodes)
}

// Shortcut: {{.FTSNode | noport}}:{{.FTSPort}}
func (t *TemplateResolver) FTSNodePort() string {
	return fmt.Sprintf("%s:%s", t.NoPort(t.FTSNode()), t.FTSPort())
}

// Shortcut: .ClusterNodes | .Service `fts` | net N
func (t *TemplateResolver) NthFTSNode(n int) string {
	nodes := t.ClusterNodes()
	serviceNodes := t.Service("fts", nodes)
	return t.Address(n, serviceNodes)
}

// Shortcut: .EventingNode | .Service `eventing` | net 0
func (t *TemplateResolver) EventingNode() string {
	nodes := t.ClusterNodes()
	serviceNodes := t.Service("eventing", nodes)
	return t.Address(0, serviceNodes)
}

// Shortcut: {{.EventingNode | noport}}:{{.EventingPort}}
func (t *TemplateResolver) EventingNodePort() string {
	return fmt.Sprintf("%s:%s", t.NoPort(t.EventingNode()), t.EventingPort())
}

// Shortcut: .ClusterNodes | .Service `eventing` | net N
func (t *TemplateResolver) NthEventingNode(n int) string {
	nodes := t.ClusterNodes()
	serviceNodes := t.Service("eventing", nodes)
	return t.Address(n, serviceNodes)
}

// Shortcut: .AnalyticsNode | .Service `analytics` | net 0
func (t *TemplateResolver) AnalyticsNode() string {
	nodes := t.ClusterNodes()
	serviceNodes := t.Service("analytics", nodes)
	return t.Address(0, serviceNodes)
}

// Shortcut: {{.AnalyticsNode | noport}}:{{.AnalyticsPort}}
func (t *TemplateResolver) AnalyticsNodePort() string {
	return fmt.Sprintf("%s:%s", t.NoPort(t.AnalyticsNode()), t.AnalyticsPort())
}

// Shortcut: .ClusterNodes | .Service `analytics` | net N
func (t *TemplateResolver) NthAnalyticsNode(n int) string {
	nodes := t.ClusterNodes()
	serviceNodes := t.Service("analytics", nodes)
	return t.Address(n, serviceNodes)
}

func (t *TemplateResolver) Attr(key string, servers []ServerSpec) string {
	attr := t.Scope.Spec.ToAttr(key)
	spec := reflect.ValueOf(servers[0])
	val := spec.FieldByName(attr).String()
	return val
}

// return test level platform
func (t *TemplateResolver) Platform() string {
	return *t.Scope.Flags.Platform
}

// Shortcut:  .ClusterNodes | .Attr `rest_username`
func (t *TemplateResolver) RestUsername() string {
	nodes := t.ClusterNodes()
	return t.Attr("rest_username", nodes)
}

// Shortcut:  .ClusterNodes | .Attr `rest_password`
func (t *TemplateResolver) RestPassword() string {
	nodes := t.ClusterNodes()
	return t.Attr("rest_password", nodes)
}

// Shortcut:  .ClusterNodes | .Attr `ram`
// Note this value adjusted by setup if %
// but if setup was not run then 256 is returned
func (t *TemplateResolver) Ram() string {
	nodes := t.ClusterNodes()
	ram := t.Attr("ram", nodes)

	// if value is still a percent then
	// resort to lowest value
	if strings.Index(ram, "%") > -1 {
		ram = "256"
	}
	return ram
}

// Shortcut:  .ClusterNodes | .Attr `ssh_username`
func (t *TemplateResolver) SSHUsername() string {
	nodes := t.ClusterNodes()
	username := t.Attr("ssh_username", nodes)
	if username == "" {
		switch *t.Scope.Flags.Platform {
		case "windows":
			username = "Administrator"
		default:
			username = "root"
		}
	}

	return username

}

// Shortcut:  .ClusterNodes | .Attr `ssh_password`
func (t *TemplateResolver) SSHPassword() string {
	nodes := t.ClusterNodes()
	password := t.Attr("ssh_password", nodes)
	if password == "" {
		switch t.Scope.GetPlatform() {
		case "windows":
			password = "Membase123"
		default:
			password = "couchbase"
		}
	}

	return password
}

// Get nodes from Cluster Spec that where:
//		isActive = true, node is in cluster
//		isActive = false, node is not in cluster
func (t *TemplateResolver) NodesByAvailability(servers []ServerSpec, isActive bool) []string {

	ips := []string{}
	for _, spec := range servers {
		for _, name := range spec.Names {
			active := !t.Scope.Rest.NodeIsSingle(name)
			if active == isActive {
				ip := t.Scope.Provider.GetHostAddress(name)
				ips = append(ips, ip)
			}
		}
	}

	return ips

}

// Get ALL nodes from Cluster Spec that are active
func (t *TemplateResolver) ActiveNodes(servers []ServerSpec) []string {
	return t.NodesByAvailability(servers, true)
}

// Get ALL nodes from Cluster Spec that are single (not active)
func (t *TemplateResolver) InActiveNodes(servers []ServerSpec) []string {
	return t.NodesByAvailability(servers, false)
}

// Get ONE node from ANY cluster where:
//		isActive = true, node is in cluster
//		isActive = false, node is not in cluster
func (t *TemplateResolver) NodeFromClusterByAvailability(n int, isActive bool, indexOverride int) string {

	servers := t.Cluster(n, t.Nodes())
	var nodes []string
	if isActive == true {
		nodes = t.ActiveNodes(servers)
	} else {
		nodes = t.InActiveNodes(servers)
	}

	numNodes := len(nodes)
	ip := "<node_not_found>"
	if numNodes > 0 {

		// get node at specific offset in list of avaialable nodes
		if indexOverride > 0 && (numNodes > indexOverride) {
			ip = nodes[indexOverride]
		} else {
			// get first node omitting orchestrator if possible
			ip = nodes[0]
			if ip == t.Orchestrator() && numNodes > 1 {
				ip = nodes[1]
			}

		}
	}

	return ip
}

// Get ONE node from FIRST cluster that is Active
func (t *TemplateResolver) ActiveNode() string {
	return t.NodeFromClusterByAvailability(0, true, 0)
}

// Get ONE node from FIRST cluster that is InActive
func (t *TemplateResolver) InActiveNode() string {
	return t.NodeFromClusterByAvailability(0, false, 0)
}

func (t *TemplateResolver) NthInActiveNode(n int) string {
	return t.NodeFromClusterByAvailability(0, false, n)
}

// Template function: `net`
func (t *TemplateResolver) Address(index int, servers []ServerSpec) string {
	if len(servers) == 0 || len(servers[0].Names) <= index {
		return "<node_not_found>"
	}

	var name = servers[0].Names[index]
	return t.Scope.Provider.GetHostAddress(name)
}

// Template function: `active`
// filters out server list to nth active node
func (t *TemplateResolver) ActiveFilter(index int, servers []ServerSpec) string {

	activeNodes := t.NodesByAvailability(servers, true)
	if len(activeNodes) <= index {
		return "<node_not_found>"
	}

	return activeNodes[index]
}

// Shortcut: .ClusterNodes | .Service `index` | active n
func (t *TemplateResolver) ActiveIndexNode(index int) string {
	nodes := t.ClusterNodes()
	serviceNodes := t.Service("index", nodes)
	return t.ActiveFilter(index, serviceNodes)
}

// Get the IP of the container
func (t *TemplateResolver) ContainerIP(alias string) string {
	// check if alias exist in scope vars
	if id, ok := t.Scope.GetVarsKV(alias); ok {
		if t.Scope.Cm.CheckContainerExists(id) {
			container, err := t.Scope.Cm.Client.InspectContainer(id)
			if err == nil {
				return container.NetworkSettings.IPAddress
			}
		}
	}
	return "<node_not_found>"
}

func (t *TemplateResolver) AuthUser(index int, servers []ServerSpec) *RbacSpec {
	for _, spec := range servers {
		for i, userSpec := range spec.RbacSpecs {
			if i == index {
				return &userSpec
			}
			i++
		}
	}
	return nil
}

// .ClusterNodes | (auth_user N).Name
func (t *TemplateResolver) NthAuthUserName(n int) string {
	if user := t.AuthUser(n, t.ClusterNodes()); user != nil {
		return user.Name
	}
	return "<user not found>"
}

// .ClusterNodes | (auth_user 0).Name
func (t *TemplateResolver) AuthUserName() string {
	return t.NthAuthUserName(0)
}

// .ClusterNodes | (auth_user N).Password
func (t *TemplateResolver) NthAuthPassword(n int) string {
	if user := t.AuthUser(n, t.ClusterNodes()); user != nil {
		return user.Password
	}
	return "<user not found>"
}

// .ClusterNodes | (auth_user 0).Password
func (t *TemplateResolver) AuthPassword() string {
	return t.NthAuthPassword(0)
}

// Template function: `bucket`
func (t *TemplateResolver) BucketName(index int, servers []ServerSpec) string {
	var i = 0
	for _, spec := range servers {
		for _, bucketSpec := range spec.BucketSpecs {
			for _, name := range bucketSpec.Names {
				if i == index {
					return name
				}
				i++
			}
		}
	}
	return "<bucket_not_found>"
}

// .ClusterNodes | bucket 0
func (t *TemplateResolver) Bucket() string {
	return t.BucketName(0, t.ClusterNodes())
}

// .ClusterNodes | bucket N
func (t *TemplateResolver) NthBucket(n int) string {
	return t.BucketName(n, t.ClusterNodes())
}

// strip port from addr
func (t *TemplateResolver) NoPort(addr string) string {
	return strings.Split(addr, ":")[0]
}

func (t *TemplateResolver) TailLogs(key string, tail int) string {
	var val string
	tailStr := strconv.Itoa(tail)

	// check if key exist in scope vars
	if id, ok := t.Scope.GetVarsKV(key); ok == true {
		// get containers return log
		val = t.Scope.Cm.GetLogs(id, tailStr)
	}
	return val
}

func (t *TemplateResolver) AllLogs(key string) string {
	var val string

	// check if key exist in scope vars
	if id, ok := t.Scope.GetVarsKV(key); ok == true {
		// get containers return log
		val = t.Scope.Cm.GetLogs(id, "all")
	}
	return val
}

func (t *TemplateResolver) Contains(key, str string) bool {
	return strings.Contains(str, key)
}

func (t *TemplateResolver) Excludes(key, str string) bool {
	return !strings.Contains(str, key)
}

func (t *TemplateResolver) ToJson(data string) interface{} {
	// from common.go
	var js interface{}
	StringToJson(data, &js)
	return js
}

func (t *TemplateResolver) ToDoubleQuotes(data string) interface{} {
	// transform all single quotes to double
	return strings.Replace(data, "'", "\"", -1)
}

func (t *TemplateResolver) WrapSingleQuote(data string) interface{} {
	// wraps input string with single quotes
	return fmt.Sprintf("'%s'", data)
}

func (t *TemplateResolver) ToList(spec ServerSpec) []ServerSpec {
	return []ServerSpec{spec}
}

func (t *TemplateResolver) StrList(args ...string) []string {
	return args
}

func (t *TemplateResolver) MkRange(args ...int) []int {
	s := []int{}
	step := 1
	if len(args) == 3 {
		step = args[2]
	}
	for i := args[0]; i <= args[1]; i += step {
		s = append(s, i)
	}

	return s
}

// returns status string of container id
func (t *TemplateResolver) FloatToInt(v float64) int {
	return int(v)
}

func (t *TemplateResolver) StrToInt(v string) int {
	i, err := strconv.Atoi(strings.TrimSpace(v))
	logerr(err)
	return i
}

// returns last item of a collection
func (t *TemplateResolver) LastItem(li []interface{}) interface{} {
	var item interface{}
	if len(li) > 0 {
		item = li[len(li)-1]
	}
	return item
}

// returns status string of container id
func (t *TemplateResolver) Status(idRef string) string {
	var status string
	var err error
	if ID, ok := t.Scope.GetVarsKV(idRef); ok == true {
		status, err = t.Scope.Cm.GetStatus(ID)
		logerr(err)
	}
	return status
}

func (t *TemplateResolver) DDoc(name string) string {
	val := "<ddoc_not_found>"
	for _, ddoc := range t.Scope.Spec.DDocs {
		if ddoc.Name == name {
			val = DDocToJson(ddoc)
		}
	}
	return val
}

// returns list of all sync gateways
func (t *TemplateResolver) SyncGateways() []SyncGatewaySpec {
	return t.Scope.Spec.SyncGateways
}

// request a specific sync gateway from list
func (t *TemplateResolver) NthSyncGateway(index int) string {
	val := ""

	// only using first set of indexes
	// TODO: additional sets can be used for xdcr cases
	syncSpecs := t.SyncGateways()
	if len(syncSpecs) > 0 {
		gateways := t.SyncGateways()[0].Names
		if len(gateways) > index {
			val = gateways[index]
		}
	}
	return val
}

// returns first sync gateway from list
func (t *TemplateResolver) SyncGateway() string {
	name := t.NthSyncGateway(0)
	val := "<sg_not_found>"
	fmt.Println(name)
	if name != "" {
		val = t.Scope.Provider.GetHostAddress(name)
	}
	return val
}

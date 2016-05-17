package sequoia

/* Template.go
 *
 * Template Resolver methods
 */

import (
	"bytes"
	"encoding/json"
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
		"net":    tResolv.Address,
		"bucket": tResolv.BucketName,
		"noport": tResolv.NoPort,
		"json":   tResolv.ToJson,
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
	return t.Scope.Aux == 0
}

func (t *TemplateResolver) EvenCount() bool {
	return (t.Scope.Aux % 2) == 0
}

func (t *TemplateResolver) OddCount() bool {
	return !t.EvenCount()
}

// apply scope scale factor to the value
func (t *TemplateResolver) Scale(val int) string {
	scale := *t.Scope.Flags.Scale
	if scale == 0 {
		scale++
	}
	return strconv.Itoa(val * scale)
}

// resolve nodes with specified service
// .Nodes | .Service `n1ql` | net 0
func (t *TemplateResolver) Service(service string, servers []ServerSpec) []ServerSpec {

	serviceNodes := []ServerSpec{}
	matchIdx := 0
	for _, spec := range servers {
		added := false
		for _, name := range spec.Names {
			rest := t.Scope.Provider.GetRestUrl(name)
			ok := NodeHasService(service, rest, spec.RestUsername, spec.RestPassword)
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

// Shortcut: {{.ClusterNodes | .Attr `query_port`}}
func (t *TemplateResolver) QueryPort() string {
	nodes := t.ClusterNodes()
	return t.Attr("query_port", nodes)
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

func (t *TemplateResolver) Attr(key string, servers []ServerSpec) string {
	attr := t.Scope.Spec.ToAttr(key)
	spec := reflect.ValueOf(servers[0])
	val := spec.FieldByName(attr).String()
	return val
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

// Template function: `net`
func (t *TemplateResolver) Address(index int, servers []ServerSpec) string {
	if len(servers) == 0 || len(servers[0].Names) <= index {
		return "<node_not_found>"
	}

	var name = servers[0].Names[index]
	return t.Scope.Provider.GetHostAddress(name)
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

func (t *TemplateResolver) Logs(key string) string {
	var val string

	// check if key exist in scope vars
	if id, ok := t.Scope.Vars[key]; ok == true {
		// get containers return log
		val = t.Scope.Cm.GetLogs(id)
	}
	return val
}

func (t *TemplateResolver) ToJson(data string) interface{} {
	var kv interface{}
	blob := []byte(data)
	err := json.Unmarshal(blob, &kv)
	logerr(err)
	return kv
}

// returns status string of container id
func (t *TemplateResolver) Status(idRef string) string {
	var status string
	var err error
	if ID, ok := t.Scope.Vars[idRef]; ok == true {
		status, err = t.Scope.Cm.GetStatus(ID)
		logerr(err)
	}
	return status
}

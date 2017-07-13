package sequoia

/*
 * Provider.go: providers provide couchbase servers to scope
 */

import (
	"fmt"
	"github.com/docker/docker/api/types/swarm"
	"github.com/fsouza/go-dockerclient"
	"strconv"
	"strings"
	"time"
)

type ProviderLabel int

const ( // iota is reset to 0
	Docker ProviderLabel = iota
	Swarm  ProviderLabel = iota
	File   ProviderLabel = iota
	Dev    ProviderLabel = iota
)

const UBUNTU_OS_DIR = "Ubuntu14"
const CENTOS_OS_DIR = "CentOS7"
const DEFAULT_DOCKER_PROVIDER_CONF = "providers/docker/options.yml"

type Provider interface {
	ProvideCouchbaseServers(filename *string, servers []ServerSpec)
	GetHostAddress(name string) string
	GetType() string
	GetRestUrl(name string) string
}

type FileProvider struct {
	Servers      []ServerSpec
	ServerNameIp map[string]string
	HostFile     string
}
type ClusterRunProvider struct {
	Servers      []ServerSpec
	ServerNameIp map[string]string
	Endpoint     string
}

type DockerProvider struct {
	Cm               *ContainerManager
	Servers          []ServerSpec
	ActiveContainers map[string]string
	StartPort        int
	Opts             *DockerProviderOpts
	ExposePorts      bool
}

type SwarmProvider struct {
	DockerProvider
}

type DockerProviderOpts struct {
	Build            string
	BuildUrlOverride string `yaml:"build_url_override"`
	CPUPeriod        int64
	CPUQuota         int64
	Memory           int64
	MemorySwap       int64
	OS               string
	Ulimits          []docker.ULimit
}

func (opts *DockerProviderOpts) MemoryMB() int {
	return int(opts.Memory / 1000000) // B -> MB
}

func NewProvider(flags TestFlags, servers []ServerSpec) Provider {
	var provider Provider
	providerArgs := strings.Split(*flags.Provider, ":")
	startPort := 8091

	switch providerArgs[0] {
	case "docker":
		cm := NewContainerManager(*flags.Client, "docker")
		if cm.ProviderType == "swarm" { // detected docker client is in a swarm
			provider = &SwarmProvider{
				DockerProvider{
					cm,
					servers,
					make(map[string]string),
					startPort,
					nil,
					*flags.ExposePorts},
			}
		} else {
			provider = &DockerProvider{
				cm,
				servers,
				make(map[string]string),
				startPort,
				nil,
				*flags.ExposePorts,
			}
		}
	case "swarm":
		cm := NewContainerManager(*flags.Client, "swarm")
		provider = &SwarmProvider{
			DockerProvider{
				cm,
				servers,
				make(map[string]string),
				startPort,
				nil,
				*flags.ExposePorts,
			},
		}
	case "file":
		hostFile := "default.yml"
		if len(providerArgs) == 2 {
			hostFile = providerArgs[1]
		}
		provider = &FileProvider{
			servers,
			make(map[string]string),
			hostFile,
		}
	case "dev":
		endpoint := "127.0.0.1"
		if len(providerArgs) == 2 {
			endpoint = providerArgs[1]
		}
		provider = &ClusterRunProvider{
			servers,
			make(map[string]string),
			endpoint,
		}
	}

	return provider
}

func (p *FileProvider) GetType() string {
	return "file"
}
func (p *FileProvider) GetHostAddress(name string) string {
	return p.ServerNameIp[name]
}

func (p *FileProvider) GetRestUrl(name string) string {
	return p.GetHostAddress(name) + ":8091"
}

func (p *FileProvider) ProvideCouchbaseServers(filename *string, servers []ServerSpec) {
	var hostNames string
	hostFile := fmt.Sprintf("providers/file/%s", p.HostFile)
	ReadYamlFile(hostFile, &hostNames)
	hosts := strings.Split(hostNames, " ")
	var i int
	for _, server := range servers {
		for _, name := range server.Names {
			if i < len(hosts) {
				p.ServerNameIp[name] = hosts[i]
			}
			i++
		}
	}
}

func (p *ClusterRunProvider) GetType() string {
	return "dev"
}
func (p *ClusterRunProvider) GetHostAddress(name string) string {
	return p.ServerNameIp[name]
}

func (p *ClusterRunProvider) GetRestUrl(name string) string {

	var i int
	for _, server := range p.Servers {
		for _, pName := range server.Names {
			if pName == name {
				port := 9000 + i
				return fmt.Sprintf("%s:%d", p.Endpoint, port)
			}
			i++
		}
	}
	return "<no_host>"
}

func (p *ClusterRunProvider) ProvideCouchbaseServers(filename *string, servers []ServerSpec) {
	var i int
	for _, server := range servers {
		for _, name := range server.Names {
			port := 9000 + i
			p.ServerNameIp[name] = fmt.Sprintf("%s:%d", p.Endpoint, port)
			i++
		}
	}
}

func (p *DockerProvider) GetType() string {
	return p.Cm.ProviderType
}

func (p *DockerProvider) GetHostAddress(name string) string {
	var ipAddress string

	id, ok := p.ActiveContainers[name]
	if ok == false {
		// look up container by name
		filter := make(map[string][]string)
		filter["name"] = []string{name}
		opts := docker.ListContainersOptions{
			Filters: filter,
		}
		containers, err := p.Cm.Client.ListContainers(opts)
		chkerr(err)
		id = containers[0].ID
	}
	container, err := p.Cm.Client.InspectContainer(id)
	chkerr(err)
	ipAddress = container.NetworkSettings.IPAddress

	return ipAddress
}

func (p *DockerProvider) NumCouchbaseServers() int {
	count := 0
	opts := docker.ListContainersOptions{All: true}
	containers, err := p.Cm.Client.ListContainers(opts)
	chkerr(err)
	for _, c := range containers {
		if strings.Index(c.Image, "couchbase") > -1 {
			count++
		}
	}
	return count
}

func (p *DockerProvider) ProvideCouchbaseServers(filename *string, servers []ServerSpec) {

	var providerOpts DockerProviderOpts
	if filename == nil || len(*filename) == 0 {
		*filename = DEFAULT_DOCKER_PROVIDER_CONF

	}
	ReadYamlFile(*filename, &providerOpts)
	p.Opts = &providerOpts
	var build = p.Opts.Build

	// start based on number of containers
	var i int = p.NumCouchbaseServers()
	p.StartPort += i
	for _, server := range servers {
		serverNameList := ExpandServerName(server.Name, server.Count, server.CountOffset+1)

		for _, serverName := range serverNameList {
			portStr := fmt.Sprintf("%d", 8091+i)
			port := docker.Port("8091/tcp")
			binding := make([]docker.PortBinding, 1)
			binding[0] = docker.PortBinding{
				HostPort: portStr,
			}

			var portBindings = make(map[docker.Port][]docker.PortBinding)
			portBindings[port] = binding
			hostConfig := docker.HostConfig{
				Ulimits:    p.Opts.Ulimits,
				Privileged: true,
			}
			if p.ExposePorts == true {
				hostConfig.PortBindings = portBindings
			}

			if p.Opts.CPUPeriod > 0 {
				hostConfig.CPUPeriod = p.Opts.CPUPeriod
			}
			if p.Opts.CPUQuota > 0 {
				hostConfig.CPUQuota = p.Opts.CPUQuota
			}
			if p.Opts.Memory > 0 {
				hostConfig.Memory = p.Opts.Memory
			}
			if p.Opts.MemorySwap != 0 {
				hostConfig.MemorySwap = p.Opts.MemorySwap
			}

			// check if build version exists
			var osPath = UBUNTU_OS_DIR
			if p.Opts.OS == "centos7" {
				osPath = CENTOS_OS_DIR
			}
			var imgName = fmt.Sprintf("couchbase_%s.%s",
				build,
				strings.ToLower(osPath))
			exists := p.Cm.CheckImageExists(imgName)

			if exists == false {

				var buildArgs = BuildArgsForVersion(p.Opts)
				var contextDir = fmt.Sprintf("containers/couchbase/%s/", osPath)
				var buildOpts = docker.BuildImageOptions{
					Name:           imgName,
					ContextDir:     contextDir,
					SuppressOutput: false,
					Pull:           false,
					BuildArgs:      buildArgs,
				}

				// build image
				err := p.Cm.BuildImage(buildOpts)
				logerr(err)
			}

			config := docker.Config{
				Image: imgName,
			}

			options := docker.CreateContainerOptions{
				Name:       serverName,
				Config:     &config,
				HostConfig: &hostConfig,
			}

			_, container := p.Cm.RunContainer(options)
			p.ActiveContainers[container.Name] = container.ID
			colorsay("start couchbase http://" + p.GetRestUrl(serverName))
			i++
		}
	}
}

func (p *SwarmProvider) GetLinkPairs() string {
	pairs := []string{}
	for name, _ := range p.ActiveContainers {
		address := p.GetHostAddress(name)
		pairs = append(pairs, address)
	}

	return strings.Join(pairs, ",")
}

func (p *SwarmProvider) ProvideCouchbaseServer(serverName string, portOffset int, zone string) {

	var build = p.Opts.Build

	portStr := fmt.Sprintf("%d", portOffset)
	port := docker.Port("8091/tcp")
	binding := make([]docker.PortBinding, 1)
	binding[0] = docker.PortBinding{
		HostPort: portStr,
	}

	portConfig := []swarm.PortConfig{
		swarm.PortConfig{},
	}

	if p.ExposePorts {
		portConfig[0].TargetPort = 8091
		portConfig[0].PublishedPort = uint32(portOffset)
	}

	var portBindings = make(map[docker.Port][]docker.PortBinding)
	portBindings[port] = binding
	hostConfig := docker.HostConfig{
		Ulimits:    p.Opts.Ulimits,
		Privileged: true,
	}

	if p.ExposePorts {
		hostConfig.PortBindings = portBindings
	}

	if p.Opts.CPUPeriod > 0 {
		hostConfig.CPUPeriod = p.Opts.CPUPeriod
	}
	if p.Opts.CPUQuota > 0 {
		hostConfig.CPUQuota = p.Opts.CPUQuota
	}
	if p.Opts.Memory > 0 {
		hostConfig.Memory = p.Opts.Memory
	}
	if p.Opts.MemorySwap != 0 {
		hostConfig.MemorySwap = p.Opts.MemorySwap
	}

	// check if build version exists
	var osPath = UBUNTU_OS_DIR
	if p.Opts.OS == "centos7" {
		osPath = CENTOS_OS_DIR
	}
	var imgName = fmt.Sprintf("couchbase_%s.%s",
		build,
		strings.ToLower(osPath))
	exists := p.Cm.CheckImageExists(imgName)
	if exists == false {

		var buildArgs = BuildArgsForVersion(p.Opts)
		var contextDir = fmt.Sprintf("containers/couchbase/%s/", osPath)
		var buildOpts = docker.BuildImageOptions{
			Name:           imgName,
			ContextDir:     contextDir,
			SuppressOutput: false,
			Pull:           false,
			BuildArgs:      buildArgs,
		}

		// build image
		err := p.Cm.BuildImage(buildOpts)
		logerr(err)
	}

	serviceName := strings.Replace(serverName, ".", "-", -1)
	containerSpec := swarm.ContainerSpec{Image: imgName}
	placement := swarm.Placement{Constraints: []string{"node.labels.zone == " + zone}}
	taskSpec := swarm.TaskSpec{ContainerSpec: &containerSpec, Placement: &placement}
	annotations := swarm.Annotations{Name: serviceName}
	endpointSpec := swarm.EndpointSpec{Ports: portConfig}
	spec := swarm.ServiceSpec{
		Annotations:  annotations,
		TaskTemplate: taskSpec,
		EndpointSpec: &endpointSpec,
	}

	options := docker.CreateServiceOptions{
		ServiceSpec: spec,
	}

	_, container, _ := p.Cm.RunContainerAsService(options, 30)
	p.ActiveContainers[serverName] = container.ID

	colorsay("start couchbase http://" + p.GetRestUrl(serverName))
}

func (p *SwarmProvider) ProvideCouchbaseServers(filename *string, servers []ServerSpec) {

	if filename == nil || len(*filename) == 0 {
		*filename = DEFAULT_DOCKER_PROVIDER_CONF
	}

	// read provider options
	var providerOpts DockerProviderOpts
	ReadYamlFile(*filename, &providerOpts)
	p.Opts = &providerOpts

	// start based on number of containers
	var i int = p.NumCouchbaseServers()
	p.StartPort = 8091 + i
	var j = 0
	for _, server := range servers {
		serverNameList := ExpandServerName(server.Name, server.Count, server.CountOffset+1)
		for _, serverName := range serverNameList {
			port := 8091 + i

			// determine zone based on service
			services := server.NodeServices[serverName]
			zone := services[0]
			if p.Cm.NumClients() == 1 {
				zone = "client" // override for single host swarm
			}
			go p.ProvideCouchbaseServer(serverName, port, zone)
			i++
			j++
		}
	}

	for len(p.ActiveContainers) != j {
		time.Sleep(time.Second * 1)
	}
	time.Sleep(time.Second * 5)
}

func (p *SwarmProvider) GetHostAddress(name string) string {
	var ipAddress string

	id, ok := p.ActiveContainers[name]
	client := p.Cm.ClientForContainer(id)
	if ok == false {
		// look up container by name if not known
		filter := make(map[string][]string)
		filter["id"] = []string{id}
		opts := docker.ListContainersOptions{
			Filters: filter,
		}
		containers, err := client.ListContainers(opts)
		chkerr(err)
		id = containers[0].ID
	}

	container, err := client.InspectContainer(id)
	chkerr(err)
	ipAddress = container.NetworkSettings.Networks["ingress"].IPAddress

	return ipAddress
}

func (p *SwarmProvider) GetRestUrl(name string) string {
	// get ip address of the container and format as rest url

	retry := 5
	address := p.GetHostAddress(name)
	for address == "" && retry > 0 {
		// retry if ip was not found

		time.Sleep(time.Second * 3)
		address = p.GetHostAddress(name)
		retry -= 1
	}
	addr := fmt.Sprintf("%s:8091", address)
	return addr
}

func (p *SwarmProvider) GetType() string {
	return "swarm"
}

func (p *DockerProvider) GetLinkPairs() string {
	pairs := []string{}
	for name, _ := range p.ActiveContainers {
		pairs = append(pairs, name)
	}
	return strings.Join(pairs, ",")
}

func (p *DockerProvider) GetRestUrl(name string) string {

	addr := fmt.Sprintf("%s:8091", p.GetHostAddress(name))
	return addr
}

func BuildArgsForVersion(opts *DockerProviderOpts) []docker.BuildArg {

	// create options based on provider settings and build
	var buildArgs []docker.BuildArg
	var version = strings.Split(opts.Build, "-")
	if len(version) == 1 {
		logerrstr(fmt.Sprintf("unexpected build format: [%s] i.e '4.5.0-1221' required", opts.Build))
	}
	var ver = version[0]
	var build = version[1]

	var buildNoArg = docker.BuildArg{
		Name:  "BUILD_NO",
		Value: build,
	}
	var versionArg = docker.BuildArg{
		Name:  "VERSION",
		Value: ver,
	}
	var flavorArg = docker.BuildArg{
		Name:  "FLAVOR",
		Value: versionFlavor(ver),
	}

	buildArgs = []docker.BuildArg{versionArg, buildNoArg, flavorArg}
	if opts.Memory > 0 {
		ramMB := strconv.Itoa(opts.MemoryMB())
		var memArg = docker.BuildArg{
			Name:  "MEMBASE_RAM_MEGS",
			Value: ramMB,
		}
		buildArgs = append(buildArgs, memArg)
	}

	// add build url override if applicable
	if opts.BuildUrlOverride != "" {
		buildArgs = append(buildArgs,
			docker.BuildArg{
				Name:  "BUILD_URL",
				Value: opts.BuildUrlOverride,
			},
		)
		var buildParts = strings.Split(opts.BuildUrlOverride, "/")
		var buildPkg = buildParts[len(buildParts)-1]
		buildArgs = append(buildArgs,
			docker.BuildArg{
				Name:  "BUILD_PKG",
				Value: buildPkg,
			},
		)
	}
	return buildArgs

}

func versionFlavor(ver string) string {
	switch true {
	case strings.Index(ver, "4.1") == 0:
		return "sherlock"
	case strings.Index(ver, "4.5") == 0:
		return "watson"
	case strings.Index(ver, "4.6") == 0:
		return "watson"
	case strings.Index(ver, "4.7") == 0:
		return "spock"
	case strings.Index(ver, "5.0") == 0:
		return "spock"
	}
	return "spock"
}

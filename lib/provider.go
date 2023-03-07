package sequoia

/*
 * Provider.go: providers provide couchbase servers to scope
 */

import (
	"context"
	"fmt"
	"strconv"
	"strings"
	"time"
	"io/ioutil"
	"github.com/docker/docker/api/types/swarm"
	docker "github.com/fsouza/go-dockerclient"
	"net"
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
	ProvideSyncGateways(syncGateways []SyncGatewaySpec)
	ProvideAccels(accels []AccelSpec)
	ProvideLoadBalancer(loadBalancer LoadBalancerSpec)
	GetHostAddress(name string) string
	GetType() string
	GetRestUrl(name string) string
}

type FileProvider struct {
	Servers      []ServerSpec
	SyncGateways []SyncGatewaySpec
	ServerNameIp map[string]string
	HostFile     string
	Flags        *TestFlags
}
type ClusterRunProvider struct {
	Servers      []ServerSpec
	SyncGateways []SyncGatewaySpec
	ServerNameIp map[string]string
	Endpoint     string
}

type DockerProvider struct {
	Cm               *ContainerManager
	Servers          []ServerSpec
	SyncGateways     []SyncGatewaySpec
	Accels           []AccelSpec
	LoadBalancer     LoadBalancerSpec
	ActiveContainers map[string]string
	StartPort        int
	Opts             *DockerProviderOpts
	Flags            *TestFlags
}

type SwarmProvider struct {
	DockerProvider
}

type DockerProviderOpts struct {
	Build              string
	SyncGatewayVersion string `yaml:"sync_gateway_version"`
	AccelVersion       string `yaml:"accel_version"`
	BuildUrlOverride   string `yaml:"build_url_override"`
	CPUPeriod          int64
	CPUQuota           int64
	Memory             int64
	MemorySwap         int64
	OS                 string
	Ulimits            []docker.ULimit
}

func (opts *DockerProviderOpts) MemoryMB() int {
	return int(opts.Memory / 1000000) // B -> MB
}

func NewProvider(flags TestFlags, servers []ServerSpec, syncGateways []SyncGatewaySpec, accels []AccelSpec, loadBalancer LoadBalancerSpec) Provider {
	var provider Provider
	providerArgs := strings.Split(*flags.Provider, ":")
	startPort := 8091

	switch providerArgs[0] {
	case "docker":
		cm := NewContainerManager(*flags.Client, "docker", *flags.Network)

		if cm.ProviderType == "swarm" { // detected docker client is in a swarm
			provider = &SwarmProvider{
				DockerProvider{
					cm,
					servers,
					syncGateways,
					accels,
					loadBalancer,
					make(map[string]string),
					startPort,
					nil,
					&flags,
				},
			}
		} else {
			provider = &DockerProvider{
				cm,
				servers,
				syncGateways,
				accels,
				loadBalancer,
				make(map[string]string),
				startPort,
				nil,
				&flags,
			}
		}
	case "swarm":

		// TODO: implement network on Swarm
		network := *flags.Network
		if network != "" {
			panic("Docker network not implemented on Swarm")
		}

		cm := NewContainerManager(*flags.Client, "swarm", "")

		provider = &SwarmProvider{
			DockerProvider{
				cm,
				servers,
				syncGateways,
				accels,
				loadBalancer,
				make(map[string]string),
				startPort,
				nil,
				&flags,
			},
		}
	case "file":
		hostFile := "default.yml"
		if len(providerArgs) == 2 {
			hostFile = providerArgs[1]
		}
		provider = &FileProvider{
			servers,
			syncGateways,
			make(map[string]string),
			hostFile,
			&flags,
		}
	case "dev":
		endpoint := "127.0.0.1"
		if len(providerArgs) == 2 {
			endpoint = providerArgs[1]
		}
		provider = &ClusterRunProvider{
			servers,
			syncGateways,
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
	var host string
	var port string
	var scheme string
	if *p.Flags.TLS || *p.Flags.Capella {
		port = "18091"
		scheme = "https"
	} else {
		port = "8091"
		scheme = "http"
	}
	if *p.Flags.Capella {
		cname, srvs , err := net.LookupSRV("couchbases", "tcp", p.ServerNameIp[name])
		if err != nil {
			fmt.Printf("\ncname: %s\n", cname)
			panic(err)
		}
		for _, srv := range srvs {
			host = strings.Trim(srv.Target, ".")
		}
	} else {
		host = p.GetHostAddress(name)
	}
	add := scheme + "://" + host + ":" + port
	return add
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
				parts := strings.Split(hosts[i], ":")
				prefix := parts[0]
				if prefix != "syncgateway" {
					p.ServerNameIp[name] = hosts[i]
				}
			}
			i++
		}
	}
}

func (p *FileProvider) ProvideSyncGateways(syncGateways []SyncGatewaySpec) {
	// If user specifies FileProvider and includes a Sync Gateway Spec
	// lookup yml keys prefixed with 'syncgateway'
	var hostNames string
	hostFile := fmt.Sprintf("providers/file/%s", p.HostFile)
	ReadYamlFile(hostFile, &hostNames)
	hosts := strings.Split(hostNames, " ")
	gatewayHosts := []string{}
	for _, host := range hosts {
		parts := strings.Split(host, ":")
		prefix := parts[0]
		if prefix == "syncgateway" {
			if len(parts) > 1 {
				ip := parts[1]
				gatewayHosts = append(gatewayHosts, ip)
			}
		}
	}

	// provide an ip for each gateway
	var j int
	for _, syncGateway := range syncGateways {

		syncGatewayNameList := ExpandServerName(syncGateway.Name, syncGateway.Count, syncGateway.CountOffset+1)
		for _, syncGatewayName := range syncGatewayNameList {

			var i int
			if i < len(gatewayHosts) {
				p.ServerNameIp[syncGatewayName] = gatewayHosts[i+j]
			}
			i++
		}
		j++
	}

}

// ProvideSyncGateways should work with FileProvider (TODO)
func (p *FileProvider) ProvideAccels(accels []AccelSpec) {
	// If user specifies FileProvider and includes a Sync Gateway Spec, panic
	// until this is supported
	if len(accels) > 0 {
		panic("Unsupported provider (FileProvider) for Accel")
	}
}

// ProvideLoadBalancer should work with FileProvider (TODO)
func (p *FileProvider) ProvideLoadBalancer(loadBalancer LoadBalancerSpec) {
	// TODO
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

// ProvideSyncGateways should work with ClusterRunProvider (TODO)
func (p *ClusterRunProvider) ProvideSyncGateways(syncGateways []SyncGatewaySpec) {
	// If user specifies FileProvider and includes a Accel Spec, panic
	// until this is supported
	if len(syncGateways) > 0 {
		panic("Unsupported provider (ClusterRunProvider) for Accel")
	}
}

// ProvideAccels should work with ClusterRunProvider (TODO)
func (p *ClusterRunProvider) ProvideAccels(accels []AccelSpec) {
	// If user specifies FileProvider and includes a Accel Spec, panic
	// until this is supported
	if len(accels) > 0 {
		panic("Unsupported provider (ClusterRunProvider) for Accel")
	}
}

// ProvideLoadBalancer should work with ClusterRunProvider (TODO)
func (p *ClusterRunProvider) ProvideLoadBalancer(loadBalancer LoadBalancerSpec) {
	// TODO
}

func (p *DockerProvider) GetType() string {
	return p.Cm.ProviderType
}

func (p *DockerProvider) UseNetwork() bool {
	return *p.Flags.Network != ""
}

func (p *DockerProvider) ExposePorts() bool {
	return *p.Flags.ExposePorts
}

func (p *DockerProvider) CreateNetwork(name string) {
	p.Cm.CreateNetwork(name)
}

func (p *DockerProvider) GetHostAddress(name string) string {

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

	var host string
	if !p.UseNetwork() {
		host = container.NetworkSettings.IPAddress
	} else {
		// strip the prefix "/"
		host = container.Name[1:]
	}

	return host
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
	// create network if specified
	if p.UseNetwork() {
		p.CreateNetwork(*p.Flags.Network)
	}

	ReadYamlFile(*filename, &providerOpts)
	p.Opts = &providerOpts
	ApplyFlagOverrides(*p.Flags.Override, p.Opts)
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
			if p.ExposePorts() == true {
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

			if exists == false || (p.Opts.BuildUrlOverride != "") {

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

// BuildMobileContainer will check to see if local image is already built
// for "syncgateway" or "accel" product given the versions provided via options
// If the image does not exist locally, sequoia will build it
func (p *DockerProvider) BuildMobileContainer(options *DockerProviderOpts, product string) docker.Config {

	var osPath = ""
	if options.OS == "centos7" {
		osPath = CENTOS_OS_DIR
	} else {
		panic("Sync Gateway only supports Centos7 for now")
	}

	var version string
	if product == "syncgateway" {
		version = options.SyncGatewayVersion
	} else if product == "accel" {
		version = options.AccelVersion
	} else {
		panic("Unsupported Mobile product: Should be 'syncgateway' or 'accel'")
	}

	imgName := fmt.Sprintf("%s_%s.%s",
		product,
		version,
		strings.ToLower(osPath))

	exists := p.Cm.CheckImageExists(imgName)

	if exists == false {

		var buildArgs = BuildArgsForMobileVersion(version)
		var contextDir = fmt.Sprintf("containers/%s/%s/", product, osPath)
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

	return config

}

// StartMobileContainer will run the following steps
//  1. Get Couchbase Server url from the first host.
//  2. Start the Sync Gateway pointing at Couchbase Server
//
//  IMPORTANT: This should only be called once we know there are at
//    least one Couchbase Server running.
func (p *DockerProvider) StartMobileContainer(containerName string, config docker.Config) string {

	// If network is not provided, link pairs so that the Sync Gateway container can talk to server
	var linkPairs []string
	if !p.UseNetwork() {
		linkPairsString := p.GetLinkPairs()
		linkPairs = strings.Split(linkPairsString, ",")
	} else {
		linkPairs = []string{}
	}

	hostConfig := docker.HostConfig{
		Privileged: true,
		Links:      linkPairs,
	}

	// Run SG container detached
	ctx := context.Background()
	options := docker.CreateContainerOptions{
		Name:       containerName,
		Config:     &config,
		HostConfig: &hostConfig,
		Context:    ctx,
	}

	// Start the container
	_, container := p.Cm.RunContainer(options)
	p.ActiveContainers[container.Name] = container.ID
	colorsay(fmt.Sprintf("starting http://%s:4984", container.Name))

	return container.ID
}

// ProvideSyncGateways will build and start all sync gateway containers
func (p *DockerProvider) ProvideSyncGateways(syncGateways []SyncGatewaySpec) {

	var providerOpts DockerProviderOpts
	ReadYamlFile("providers/docker/options.yml", &providerOpts)

	// Check to see if the container exists locally. Build if it is not present
	config := p.BuildMobileContainer(&providerOpts, "syncgateway")

	for _, syncGateway := range syncGateways {

		syncGatewayNameList := ExpandServerName(syncGateway.Name, syncGateway.Count, syncGateway.CountOffset+1)

		for _, syncGatewayName := range syncGatewayNameList {

			// Start the containers
			containerID := p.StartMobileContainer(syncGatewayName, config)

			// Get the ip address of the first server in the group
			cbsURL := p.Servers[0].Names[0]

			// Mode is required to write the Sync Gateway config for
			// "di" = distributed index modes (Accels)
			// "cc" = channel cache mode (Standalone)
			var mode string
			if len(p.Accels) > 0 {
				mode = "di"
			} else {
				mode = "cc"
			}

			// Start Sync Gateway service
			cmd := []string{"./entrypoint.sh", cbsURL, mode}
			colorsay(fmt.Sprintf("exec %s on %s", cmd, containerID))
			p.Cm.ExecContainer(containerID, cmd, true)
		}
	}
}

// ProvideAccels will build and start all sync gateway containers
func (p *DockerProvider) ProvideAccels(accels []AccelSpec) {

	var providerOpts DockerProviderOpts
	ReadYamlFile("providers/docker/options.yml", &providerOpts)

	// Check to see if the container exists locally. Build if it is not present
	config := p.BuildMobileContainer(&providerOpts, "accel")

	for _, accel := range accels {

		accelNameList := ExpandServerName(accel.Name, accel.Count, accel.CountOffset+1)

		for _, accelName := range accelNameList {

			// Start the containers
			containerID := p.StartMobileContainer(accelName, config)

			// Get the ip address of the first server in the group
			cbsURL := p.Servers[0].Names[0]

			// Start Sync Gateway service
			cmd := []string{"./entrypoint.sh", cbsURL}
			colorsay(fmt.Sprintf("exec %s on %s", cmd, containerID))
			p.Cm.ExecContainer(containerID, cmd, true)
		}
	}
}

// ProvideLoadBalancer should work with SwarmProvider (TODO)
func (p *DockerProvider) ProvideLoadBalancer(loadBalancer LoadBalancerSpec) {
	// TODO
	if loadBalancer.Name != "" {

		// Pull image if it does not exist
		imgName := "nginx"
		exists := p.Cm.CheckImageExists(imgName)
		if !exists {
			p.Cm.PullImage(imgName)
		}

		// Read template nginx config and Add Sync Gateway endpoint
		bytes, err := ioutil.ReadFile("containers/syncgateway/nginx.conf.j2.template")
		chkerr(err)

		// Build string of Sync Gateway endpoints
		var syncGatewayEndpoints string
		var syncGatewayAdminEndpoints string
		for _, syncGateway := range p.SyncGateways {
			for _, syncGatewayName := range syncGateway.Names {
				colorsay(fmt.Sprintf("Adding %s:4984 to load balancer", syncGatewayName))
				syncGatewayEndpoints += fmt.Sprintf("server %s:4984;\n", syncGatewayName)
				syncGatewayAdminEndpoints += fmt.Sprintf("server %s:4985;\n", syncGatewayName)
			}
		}

		// Render the Sync Gateway enpoints
		nginxConf := string(bytes)
		nginxConf = strings.Replace(nginxConf, "PUBLIC_UPSTREAM_SYNCGATEWAYS", syncGatewayEndpoints, -1)
		nginxConf = strings.Replace(nginxConf, "ADMIN_UPSTREAM_SYNCGATEWAYS", syncGatewayAdminEndpoints, -1)

		// Write the rendered file
		err = ioutil.WriteFile("containers/syncgateway/nginx.conf.j2", []byte(nginxConf), 0644)
		chkerr(err)

		// Run the nginx container
		volumes := BuildVolumes("containers/syncgateway/nginx.conf.j2:/etc/nginx/nginx.conf:ro")

		// Setup container options
		config := docker.Config{
			Image: imgName,
		}

		hostConfig := docker.HostConfig{
			Binds: volumes,
		}

		opts := docker.CreateContainerOptions{
			Name:       loadBalancer.Name,
			Config:     &config,
			HostConfig: &hostConfig,
		}

		// Run the load balancer
		colorsay("Running nginx load balancer")
		p.Cm.RunContainer(opts)
	}
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

	if p.ExposePorts() {
		portConfig[0].TargetPort = 8091
		portConfig[0].PublishedPort = uint32(portOffset)
	}

	var portBindings = make(map[docker.Port][]docker.PortBinding)
	portBindings[port] = binding
	hostConfig := docker.HostConfig{
		Ulimits:    p.Opts.Ulimits,
		Privileged: true,
	}

	if p.ExposePorts() {
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
	taskSpec := swarm.TaskSpec{ContainerSpec: &containerSpec}
	endpointSpec := swarm.EndpointSpec{}

	// put on ingress network
	networks := []swarm.NetworkAttachmentConfig{}
	if p.ExposePorts() {
		networks = append(networks, swarm.NetworkAttachmentConfig{Target: "ingress"})
		endpointSpec = swarm.EndpointSpec{Ports: portConfig}
	}

	if p.Flags.Network != nil {
		network := swarm.NetworkAttachmentConfig{Target: *p.Flags.Network}
		networks = append(networks, network)
		taskSpec.Networks = networks
	}
	annotations := swarm.Annotations{Name: serviceName}

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

// ProvideSyncGateways should work with Swarm (TODO)
func (p *SwarmProvider) ProvideSyncGateways(syncGateways []SyncGatewaySpec) {
	// If user specifies FileProvider and includes a Sync Gateway Spec, panic
	// until this is supported
	if len(syncGateways) > 0 {
		panic("Unsupported provider (SwarmProvider) for Sync Gateway")
	}
}

// ProvideAccels should work with Swarm (TODO)
func (p *SwarmProvider) ProvideAccels(accels []AccelSpec) {
	// If user specifies FileProvider and includes a Accel Spec, panic
	// until this is supported
	if len(accels) > 0 {
		panic("Unsupported provider (SwarmProvider) for Accel")
	}
}

// ProvideLoadBalancer should work with SwarmProvider (TODO)
func (p *SwarmProvider) ProvideLoadBalancer(loadBalancer LoadBalancerSpec) {
	// TODO
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
	network := "ingress"
	if p.Flags.Network != nil {
		network = *p.Flags.Network
	}
	ipAddress = container.NetworkSettings.Networks[network].IPAddress

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

func BuildArgsForMobileVersion(version string) []docker.BuildArg {

	var buildArgs []docker.BuildArg
	version_parts := strings.Split(version, "-")

	var ver = version_parts[0]
	var build = version_parts[1]

	var buildNoArg = docker.BuildArg{
		Name:  "BUILD_NO",
		Value: build,
	}
	var versionArg = docker.BuildArg{
		Name:  "VERSION",
		Value: ver,
	}

	buildArgs = []docker.BuildArg{versionArg, buildNoArg}
	return buildArgs
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
	case strings.Index(ver, "5.1") == 0:
		return "spock"
	case strings.Index(ver, "5.5") == 0:
		return "vulcan"
	case strings.Index(ver, "6.0") == 0:
		return "alice"
	case strings.Index(ver, "6.5") == 0:
		return "mad-hatter"
	case strings.Index(ver, "6.6") == 0:
		return "mad-hatter"
	case strings.Index(ver, "7.0") == 0:
		return "cheshire-cat"
	case strings.Index(ver, "7.1") == 0:
		return "neo"
	case strings.Index(ver, "7.2") == 0:
		return "neo"
	}
	return "spock"
}

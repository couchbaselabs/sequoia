package sequoia

/*
 * Provider.go: providers provide couchbase servers to scope
 */

import (
	"fmt"
	"github.com/fatih/color"
	"github.com/fsouza/go-dockerclient"
	"net/url"
	"regexp"
	"strings"
)

type Provider interface {
	ProvideCouchbaseServers(servers []ServerSpec)
	GetHostAddress(name string) string
	GetType() string
	GetRestUrl(name string) string
}

type FileProvider struct {
	Servers      []ServerSpec
	ServerNameIp map[string]string
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
}

type DockerProviderOpts struct {
	Build            string
	BuildUrlOverride string `yaml:"build_url_override"`
}

func NewProvider(flags TestFlags, servers []ServerSpec) Provider {
	var provider Provider
	providerArgs := strings.Split(*flags.Provider, ":")

	switch providerArgs[0] {
	case "docker":
		cm := NewContainerManager(*flags.Client)
		provider = &DockerProvider{
			cm,
			servers,
			make(map[string]string),
		}
	case "file":
		provider = &FileProvider{
			servers,
			make(map[string]string),
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

func (p *FileProvider) ProvideCouchbaseServers(servers []ServerSpec) {
	var hostNames string
	hostFile := "providers/file/hosts.yml"
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

func (p *ClusterRunProvider) ProvideCouchbaseServers(servers []ServerSpec) {
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
	return "docker"
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
	opts := docker.ListContainersOptions{}
	containers, err := p.Cm.Client.ListContainers(opts)
	chkerr(err)
	for _, c := range containers {
		if strings.Index(c.Image, "couchbase") > -1 {
			count++
		}
	}
	return count
}

func (p *DockerProvider) ProvideCouchbaseServers(servers []ServerSpec) {

	var providerOpts DockerProviderOpts
	ReadYamlFile("providers/docker/options.yml", &providerOpts)
	var build = providerOpts.Build

	// start based on number of containers
	var i int = p.NumCouchbaseServers()
	for _, server := range servers {
		serverNameList := ExpandName(server.Name, server.Count)
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
				PortBindings: portBindings,
			}

			// check if build version exists
			var imgName = fmt.Sprintf("couchbase_%s", build)
			exists := p.Cm.CheckImageExists(imgName)
			if exists == false {

				var buildArgs = BuildArgsForVersion(providerOpts)
				var buildOpts = docker.BuildImageOptions{
					Name:           imgName,
					ContextDir:     "containers/couchbase/",
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

			fmt.Println(color.CyanString("\u2192 "), color.WhiteString("ok %s", serverName))
			i++
		}
	}
}

func (p *DockerProvider) GetLinkPairs() string {
	pairs := []string{}
	for name, _ := range p.ActiveContainers {
		pairs = append(pairs, name)
	}
	return strings.Join(pairs, ",")
}

func (p *DockerProvider) GetRestUrl(name string) string {
	// extract host from endpoint
	url, err := url.Parse(p.Cm.Endpoint)
	chkerr(err)
	host := url.Host

	// remove port if specified
	re := regexp.MustCompile(`:.*`)
	host = re.ReplaceAllString(host, "")
	port := 8091
	for _, spec := range p.Servers {
		for i, server := range spec.Names {
			if server == name {
				port = port + i
			}
		}
	}
	host = fmt.Sprintf("%s:%d\n", host, port)
	return strings.TrimSpace(host)
}

func BuildArgsForVersion(opts DockerProviderOpts) []docker.BuildArg {

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
	}
	return "watson"
}

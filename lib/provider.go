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

func NewProvider(config Config, servers []ServerSpec) Provider {
	var provider Provider

	switch config.Provider {
	case "docker":
		cm := NewContainerManager(config.Client)
		provider = &DockerProvider{
			cm,
			servers,
			config.Build,
			make(map[string]string),
		}
	case "file":
		provider = &FileProvider{
			servers,
			make(map[string]string),
		}
	}

	return provider
}

type FileProvider struct {
	Servers      []ServerSpec
	ServerNameIp map[string]string
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

type DockerProvider struct {
	Cm               *ContainerManager
	Servers          []ServerSpec
	Build            string
	ActiveContainers map[string]string
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

func (p *DockerProvider) ProvideCouchbaseServers(servers []ServerSpec) {

	var i int = 0
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
			var imgName = fmt.Sprintf("couchbase_%s", p.Build)
			exists := p.Cm.CheckImageExists(imgName)
			if exists == false {

				// create options based on provider settings and build
				var version = strings.Split(p.Build, "-")
				if len(version) == 1 {
					logerrstr(fmt.Sprintf("unexpected build format: [%s] i.e '4.5.0-1221' required", p.Build))
				}
				var buildNoArg = docker.BuildArg{
					Name:  "BUILD_NO",
					Value: version[1],
				}

				var buildOpts = docker.BuildImageOptions{
					Name:           imgName,
					ContextDir:     "containers/couchbase/",
					SuppressOutput: false,
					Pull:           false,
					BuildArgs:      []docker.BuildArg{buildNoArg},
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

			container, err := p.Cm.RunContainer(options, true)
			chkerr(err)
			p.ActiveContainers[container.Name] = container.ID

			fmt.Println(color.GreenString("\u2713 "), color.WhiteString("ok start %s", serverName))
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

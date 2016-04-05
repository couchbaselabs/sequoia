package sequoia

import (
	"fmt"
	"github.com/fatih/color"
	"github.com/fsouza/go-dockerclient"
)

type Provider interface {
	ProvideCouchbaseServers(servers []ServerSpec)
	GetHostAddress(name string) string
}

func NewProvider(config Config) Provider {
	var provider Provider

	if config.Provider == "docker" {
		cm := NewContainerManager(config.Client)
		provider = &DockerProvider{
			cm,
			make(map[string]string),
		}
	}
	return provider
}

type DockerProvider struct {
	Cm               *ContainerManager
	ActiveContainers map[string]string
}

func (p *DockerProvider) GetHostAddress(name string) string {
	var ipAddress string

	if id, ok := p.ActiveContainers[name]; ok {
		container, err := p.Cm.Client.InspectContainer(id)
		chkerr(err)
		ipAddress = container.NetworkSettings.IPAddress
	}
	return ipAddress
}

func (p *DockerProvider) ProvideCouchbaseServers(servers []ServerSpec) {

	for _, server := range servers {
		serverNameList := ExpandName(server.Name, server.Count)
		for i, serverName := range serverNameList {

			portStr := fmt.Sprintf("%d", 8091+i)
			port := docker.Port(portStr + "/tcp")
			binding := make([]docker.PortBinding, 1)
			binding[0] = docker.PortBinding{
				HostPort: portStr,
			}

			var portBindings = make(map[docker.Port][]docker.PortBinding)
			portBindings[port] = binding
			hostConfig := docker.HostConfig{
				PortBindings: portBindings,
			}

			config := docker.Config{
				Image: "couchbase-watson",
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
		}
	}
}

package sequoia

import (
	"fmt"
	"github.com/fatih/color"
	"github.com/fsouza/go-dockerclient"
	"log"
	"os"
)

type ContainerTask struct {
	Description string
	Image       string
	Command     []string
	LinksTo     string
	Async       bool
}

func (t *ContainerTask) GetOptions() docker.CreateContainerOptions {

	links := fmt.Sprintf("%s:%s", t.LinksTo, t.LinksTo)
	hostConfig := docker.HostConfig{
		Links: []string{links},
	}
	config := docker.Config{
		Image: t.Image,
		Cmd:   t.Command,
	}
	return docker.CreateContainerOptions{
		Config:     &config,
		HostConfig: &hostConfig,
	}

}

type ContainerManager struct {
	Client *docker.Client
}

func NewContainerManager(clientUrl string) *ContainerManager {

	// open docker client
	path := os.Getenv("DOCKER_CERT_PATH")
	ca := fmt.Sprintf("%s/ca.pem", path)
	cert := fmt.Sprintf("%s/cert.pem", path)
	key := fmt.Sprintf("%s/key.pem", path)
	client, err := docker.NewTLSClient(clientUrl, cert, key, ca)
	chkerr(err)

	return &ContainerManager{
		Client: client,
	}
}

func (cm *ContainerManager) GetAllContainers() []docker.APIContainers {
	opts := docker.ListContainersOptions{All: true}
	containers, err := cm.Client.ListContainers(opts)
	chkerr(err)

	return containers
}

func (cm *ContainerManager) RemoveAllContainers() {
	// teardown
	for _, c := range cm.GetAllContainers() {
		opts := docker.RemoveContainerOptions{ID: c.ID, RemoveVolumes: true, Force: true}
		err := cm.Client.RemoveContainer(opts)
		chkerr(err)

		fmt.Println(color.GreenString("\u2713 "), color.WhiteString("ok remove %s", c.Names))
	}
}

func (cm *ContainerManager) RunContainer(opts docker.CreateContainerOptions, async bool) (*docker.Container, error) {
	container, err := cm.Client.CreateContainer(opts)
	cm.Client.StartContainer(container.ID, nil)
	if async == false {
		if rc, err := cm.Client.WaitContainer(container.ID); rc != 0 {
			log.Fatal("Container did not live a good life", err)
		}
	}

	return container, err
}

func (cm *ContainerManager) Run(task ContainerTask) {

	fmt.Printf("%s %s",
		color.CyanString("\u2192"),
		color.WhiteString("%s", task.Description))

	// get task options
	options := task.GetOptions()

	_, err := cm.RunContainer(options, task.Async)
	chkerr(err)

	// print result
	fmt.Printf(color.GreenString("\t\u2713\n"))
}

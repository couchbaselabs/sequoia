package sequoia

/*
 * Container.go: container manager to wrap common docker tasks
 */

import (
	"fmt"
	"github.com/fatih/color"
	"github.com/fsouza/go-dockerclient"
	"os"
	"strings"
)

type ContainerTask struct {
	Describe   string
	Image      string
	Command    []string
	LinksTo    string
	Async      bool
	Entrypoint []string
}

func (t *ContainerTask) GetOptions() docker.CreateContainerOptions {

	hostConfig := docker.HostConfig{}
	if len(t.LinksTo) > 0 {
		links := strings.Split(t.LinksTo, ",")
		pairs := []string{}
		for _, name := range links {
			pairs = append(pairs, name+":"+name)
		}
		hostConfig.Links = pairs
	}

	config := docker.Config{
		Image: t.Image,
		Cmd:   t.Command,
	}
	if len(t.Entrypoint) > 0 {
		config.Entrypoint = t.Entrypoint
	}
	return docker.CreateContainerOptions{
		Config:     &config,
		HostConfig: &hostConfig,
	}

}

type ContainerManager struct {
	Client   *docker.Client
	Endpoint string
}

func NewContainerManager(clientUrl string) *ContainerManager {

	var client *docker.Client
	var err error
	// open docker client
	if strings.Index(clientUrl, "https") > -1 {
		// with tls
		path := os.Getenv("DOCKER_CERT_PATH")
		ca := fmt.Sprintf("%s/ca.pem", path)
		cert := fmt.Sprintf("%s/cert.pem", path)
		key := fmt.Sprintf("%s/key.pem", path)
		client, err = docker.NewTLSClient(clientUrl, cert, key, ca)
		logerr(err)
	} else {
		client, err = docker.NewClient(clientUrl)
		logerr(err)
	}

	return &ContainerManager{
		Client:   client,
		Endpoint: clientUrl,
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

		fmt.Println(color.CyanString("\u2192 "), color.WhiteString("ok remove %s", c.Names))
	}
}

func (cm *ContainerManager) CheckImageExists(image string) bool {

	// list images
	var found = false
	listOpts := docker.ListImagesOptions{
		All: true,
	}
	apiImages, err := cm.Client.ListImages(listOpts)
	chkerr(err)

	// find image locally
	for _, apiImage := range apiImages {
		for _, name := range apiImage.RepoTags {
			name = strings.Split(name, ":")[0]
			match := strings.Split(image, ":")[0]
			if name == match {
				found = true
			}
		}
	}
	return found
}

func (cm *ContainerManager) PullImage(repo string) error {
	fmt.Printf("%s  %s",
		color.CyanString("\u2192"),
		color.WhiteString("pulling image %s\n", repo))

	imgOpts := docker.PullImageOptions{
		Repository: repo,
	} // TODO: tag

	return cm.Client.PullImage(imgOpts, docker.AuthConfiguration{})
}

func (cm *ContainerManager) BuildImage(opts docker.BuildImageOptions) error {
	fmt.Printf("%s  %s",
		color.CyanString("\u2192"),
		color.WhiteString("building image %s\n", opts.Name))

	// hookup io
	opts.OutputStream = os.Stdout
	return cm.Client.BuildImage(opts)
}

func (cm *ContainerManager) RunContainer(opts docker.CreateContainerOptions, async bool) (*docker.Container, error) {
	container, err := cm.Client.CreateContainer(opts)
	cm.Client.StartContainer(container.ID, nil)
	if async == false {
		if rc, _ := cm.Client.WaitContainer(container.ID); rc != 0 {
			fmt.Println(color.RedString("\n\nError on container: %s", container.Image))
			logOpts := docker.LogsOptions{
				Container:    container.ID,
				OutputStream: os.Stdout,
				ErrorStream:  os.Stderr,
				RawTerminal:  true,
				Stdout:       true,
				Stderr:       true,
			}
			cm.Client.Logs(logOpts)
		}
	}

	return container, err
}

func (cm *ContainerManager) Run(task ContainerTask) {

	fmt.Printf("%s  %s",
		color.CyanString("\u2192"),
		color.WhiteString("%s\n", task.Describe))

	// get task options
	options := task.GetOptions()

	// pull/build container if necessary
	exists := cm.CheckImageExists(task.Image)

	if exists == false {
		err := cm.PullImage(task.Image)
		logerr(err)
	}
	_, err := cm.RunContainer(options, task.Async)
	logerr(err)

}

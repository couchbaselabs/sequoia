package sequoia

/*
 * Container.go: container manager to wrap common docker tasks
 */

import (
	"fmt"
	"github.com/fatih/color"
	"github.com/fsouza/go-dockerclient"
	"io"
	"os"
	"strings"
	"time"
)

type ContainerTask struct {
	Describe    string
	Image       string
	Command     []string
	LinksTo     string
	Async       bool
	Entrypoint  []string
	Concurrency int
	Duration    time.Duration
}

func (t *ContainerTask) GetOptions() docker.CreateContainerOptions {

	hostConfig := docker.HostConfig{}
	if len(t.LinksTo) > 0 {
		links := strings.Split(t.LinksTo, ",")
		pairs := []string{}
		for i, name := range links {
			linkName := fmt.Sprintf("container-%d.st.couchbase.com", i)
			pairs = append(pairs, name+":"+linkName)
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
	TagId    map[string]string
	IDs      []string
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
		TagId:    make(map[string]string),
		IDs:      []string{},
	}
}

func (cm *ContainerManager) GetAllContainers() []docker.APIContainers {
	opts := docker.ListContainersOptions{All: true}
	containers, err := cm.Client.ListContainers(opts)
	chkerr(err)

	return containers
}

func (cm *ContainerManager) RemoveContainer(id string) error {
	opts := docker.RemoveContainerOptions{ID: id, RemoveVolumes: true, Force: true}
	return cm.Client.RemoveContainer(opts)
}

func (cm *ContainerManager) RemoveAllContainers() {
	// teardown
	for _, c := range cm.GetAllContainers() {
		err := cm.RemoveContainer(c.ID)
		chkerr(err)

		fmt.Println(color.CyanString("\u2192 "), color.WhiteString("ok remove %s", c.Names))
	}
}
func (cm *ContainerManager) RemoveManagedContainers() {
	// teardown managed containers
	for _, id := range cm.IDs {
		err := cm.RemoveContainer(id)
		chkerr(err)

		fmt.Println(color.CyanString("\u2192 "), color.WhiteString("ok remove %s", id))
	}
}
func (cm *ContainerManager) ListImages() []docker.APIImages {

	listOpts := docker.ListImagesOptions{
		All: true,
	}
	apiImages, err := cm.Client.ListImages(listOpts)
	logerr(err)

	return apiImages
}

func (cm *ContainerManager) CheckImageExists(image string) bool {

	// list images
	apiImages := cm.ListImages()

	// find image locally
	var found = false
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
		color.WhiteString("pull %s\n", repo))

	imgOpts := docker.PullImageOptions{
		Repository: repo,
	} // TODO: tag

	return cm.Client.PullImage(imgOpts, docker.AuthConfiguration{})
}

func (cm *ContainerManager) PullTaggedImage(repo, tag string) {

	// attempt to pull tagged image
	err := cm.PullImage(repo + ":" + tag)

	// no such repo - use latest
	if err != nil {
		err := cm.PullImage(repo)
		logerr(err)
	}

	// remove any other images with different tags
	for _, apiImage := range cm.ListImages() {
		for _, name := range apiImage.RepoTags {
			imgRepo := strings.Split(name, ":")[0]
			if imgRepo == repo {
				imgTag := strings.Split(name, ":")[1]
				if imgTag == tag {
					// save tag for future use against this repo
					var tagId = apiImage.ID
					tagArgs := strings.Split(apiImage.ID, ":")
					if len(tagArgs) > 1 {
						tagId = tagArgs[1]
					}
					cm.TagId[repo] = tagId[:7]
				}
			}
		}
	}

}

func (cm *ContainerManager) BuildImage(opts docker.BuildImageOptions) error {
	fmt.Printf("%s  %s",
		color.CyanString("\u2192"),
		color.WhiteString("building image %s\n", opts.Name))

	// hookup io
	opts.OutputStream = os.Stdout
	return cm.Client.BuildImage(opts)
}

func (cm *ContainerManager) LogContainer(ID string, output io.Writer) {

	logOpts := docker.LogsOptions{
		Container:    ID,
		OutputStream: output,
		ErrorStream:  os.Stderr,
		RawTerminal:  true,
		Follow:       true,
		Stdout:       true,
		Stderr:       true,
	}
	go cm.Client.Logs(logOpts)
}

func (cm *ContainerManager) WaitContainer(container *docker.Container, c chan string) {

	// wait for container
	rc, _ := cm.Client.WaitContainer(container.ID)
	if rc != 0 && rc != 137 {
		// log on error
		fmt.Println(color.RedString("\n\nError occurred on container, try: 'docker logs " + container.ID + "'"))
		cm.LogContainer(container.ID, os.Stdout)
	}

	// remove container log
	c <- container.ID
}

func (cm *ContainerManager) ContainerLogFile(opts docker.CreateContainerOptions, ID string) string {
	return fmt.Sprintf("%s_%s", ParseSlashString(opts.Config.Image), ID[:6])
}

func (cm *ContainerManager) RunContainer(opts docker.CreateContainerOptions) (chan string, *docker.Container) {
	container, err := cm.Client.CreateContainer(opts)
	logerr(err)

	c := make(chan string)

	// start container
	cm.Client.StartContainer(container.ID, nil)
	go cm.WaitContainer(container, c)

	// save ID
	cm.IDs = append(cm.IDs, container.ID)

	// log
	f := CreateFile(cm.ContainerLogFile(opts, container.ID))
	cm.LogContainer(container.ID, f)

	return c, container
}

func (cm *ContainerManager) Run(task ContainerTask) {

	// use repo tag if exists
	if tagId, ok := cm.TagId[task.Image]; ok {
		task.Image = tagId
	} else {

		// pull/build container if necessary
		exists := cm.CheckImageExists(task.Image)

		if exists == false {
			err := cm.PullImage(task.Image)
			logerr(err)
		}

	}

	// get task options
	options := task.GetOptions()

	// run container
	printDesc(task.Describe)
	ch, container := cm.RunContainer(options)
	idChans := []chan string{ch}
	containers := []*docker.Container{container}

	// start additional containers with support for concurrency
	if task.Concurrency > 0 {
		for i := 1; i < task.Concurrency; i++ {
			printDesc(task.Describe)
			ch, container := cm.RunContainer(options)
			idChans = append(idChans, ch)
			containers = append(containers, container)
		}
	}

	// stop after duration
	if task.Duration > 0 {
		go func() {
			time.Sleep(task.Duration * time.Second)
			// remove container
			for _, c := range containers {
				cm.RemoveContainer(c.ID)
			}
		}()
	}

	// wait if necessary
	if task.Async == false {
		for _, ch := range idChans {
			<-ch
		}
	}
}

func printDesc(desc string) {
	fmt.Printf("%s  %s",
		color.CyanString("\u2192"),
		color.WhiteString("%s\n", desc))
}

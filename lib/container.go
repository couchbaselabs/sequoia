package sequoia

/*
 * Container.go: container manager to wrap common docker tasks
 */

import (
	"errors"
	"fmt"
	"github.com/fatih/color"
	"github.com/fsouza/go-dockerclient"
	"github.com/tahmmee/tap.go"
	"io"
	"os"
	"strings"
	"time"
)

type ContainerTask struct {
	Name        string
	Describe    string
	Image       string
	Command     []string
	LinksTo     string
	Async       bool
	Entrypoint  []string
	Concurrency int
	Duration    time.Duration
	LogLevel    int
	LogDir      string
}

type TaskResult struct {
	ID      string
	Image   string
	Command []string
	Error   error
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

	containerOpts := docker.CreateContainerOptions{
		Config:     &config,
		HostConfig: &hostConfig,
	}

	if t.Name != "" {
		containerOpts.Name = t.Name
	}

	return containerOpts

}

type ContainerManager struct {
	Client    *docker.Client
	Endpoint  string
	TagId     map[string]string
	IDs       []string
	TapHandle *tap.T
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
		Client:    client,
		Endpoint:  clientUrl,
		TagId:     make(map[string]string),
		IDs:       []string{},
		TapHandle: tap.New(),
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

func (cm *ContainerManager) KillContainer(id string) error {
	c, err := cm.Client.InspectContainer(id)
	if err == nil {
		// must already be running
		if c.State.Running == true {
			opts := docker.KillContainerOptions{ID: id}
			err = cm.Client.KillContainer(opts)
		}
	}
	return err
}

func (cm *ContainerManager) RemoveAllContainers() {
	// teardown
	for _, c := range cm.GetAllContainers() {
		err := cm.RemoveContainer(c.ID)
		chkerr(err)
		fmt.Println(color.CyanString("\u2192 "), color.WhiteString("remove %s", c.Names[0]))
	}
}
func (cm *ContainerManager) RemoveManagedContainers(soft bool) {
	// teardown managed containers
	for _, id := range cm.IDs {
		if soft == false {
			err := cm.RemoveContainer(id)
			chkerr(err)
			fmt.Println(color.CyanString("\u2192 "), color.WhiteString("remove %s", id[:6]))
		} else {
			err := cm.KillContainer(id)
			if err == nil {
				fmt.Println(color.CyanString("\u2192 "), color.WhiteString("kill %s", id[:6]))
			}
		}
	}
}

func (cm *ContainerManager) SaveContainerLogs(logDir string) {
	// save logs if not already saved
	for n, id := range cm.IDs {
		imgName := fmt.Sprintf("couchbase-server-%d", n)
		archive := fmt.Sprintf("%s.tar", cm.ContainerLogFile(imgName, id))
		f := CreateFile(logDir, archive)
		opts := docker.DownloadFromContainerOptions{
			OutputStream: f,
			Path:         "/opt/couchbase/var/lib/couchbase/logs",
		}
		cm.Client.DownloadFromContainer(id, opts)
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
	cm.TapHandle.Ok(true, UtilTaskMsg("[get]", repo))
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

func (cm *ContainerManager) LogContainer(ID string, output io.Writer, follow bool) {

	logOpts := docker.LogsOptions{
		Container:    ID,
		OutputStream: output,
		ErrorStream:  os.Stderr,
		RawTerminal:  true,
		Follow:       follow,
		Stdout:       true,
		Stderr:       true,
	}
	cm.Client.Logs(logOpts)
}

func (cm *ContainerManager) WaitContainer(container *docker.Container, c chan TaskResult) {

	// wait for container
	rc, _ := cm.Client.WaitContainer(container.ID)

	// get additional info about container
	container, err := cm.Client.InspectContainer(container.ID)
	logerr(err)

	// create task result
	tResult := TaskResult{
		ID:      container.ID,
		Image:   container.Config.Image,
		Command: container.Config.Cmd,
		Error:   nil,
	}

	if rc != 0 && rc != 137 {
		// log on error
		emsg := fmt.Sprintf("%s%s\n%s\n",
			"\n\nError occurred on container, try:\n",
			"docker logs "+container.ID[:6],
			"docker start "+container.ID[:6])
		fmt.Println(color.RedString(emsg))
		cm.LogContainer(container.ID, os.Stdout, false)
		tResult.Error = errors.New(fmt.Sprintf("%d", rc))
	}

	// remove container log
	c <- tResult
}

func (cm *ContainerManager) ContainerLogFile(image, ID string) string {
	return fmt.Sprintf("%s_%s", ParseSlashString(image), ID[:6])
}

func (cm *ContainerManager) RunContainer(opts docker.CreateContainerOptions) (chan TaskResult, *docker.Container) {
	container, err := cm.Client.CreateContainer(opts)
	logerr(err)

	c := make(chan TaskResult)

	// start container
	err = cm.Client.StartContainer(container.ID, nil)
	logerr(err)

	go cm.WaitContainer(container, c)

	// save ID
	cm.IDs = append(cm.IDs, container.ID)

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
	ch, container := cm.RunContainer(options)
	idChans := []chan TaskResult{ch}
	containers := []*docker.Container{container}
	cm.TapHandle.Ok(true, RunTaskMsg(task.Image, task.Command))

	// start additional containers with support for concurrency
	if task.Concurrency > 0 {
		for i := 1; i < task.Concurrency; i++ {
			PrintDesc(task.Describe)
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

	// logging
	if task.LogLevel > 0 {
		f := CreateFile(task.LogDir,
			cm.ContainerLogFile(task.Image, container.ID))
		go cm.LogContainer(container.ID, f, true)

		// send to stdout
		if task.LogLevel > 1 {
			go cm.LogContainer(container.ID, os.Stdout, true)
		}
	}

	// wait if necessary
	if task.Async == false {
		cm.HandleResults(idChans)
	} else {
		go cm.HandleResults(idChans)
	}
}

func (cm *ContainerManager) HandleResults(idChans []chan TaskResult) {
	for _, ch := range idChans {
		rc := <-ch
		if rc.Error == nil {
			cm.TapHandle.Ok(true, EndTaskMsg(rc.Image, rc.Command))
		} else {
			cm.TapHandle.Ok(false, rc.ID[:6])
		}
	}
}

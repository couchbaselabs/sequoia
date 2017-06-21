package sequoia

/*
 * Container.go: container manager to wrap common docker tasks
 */

import (
	"bytes"
	"errors"
	"fmt"
	"io"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/docker/docker/api/types/swarm"
	"github.com/fsouza/go-dockerclient"
	"github.com/streamrail/concurrent-map"
	"github.com/tahmmee/tap.go"
)

type ContainerTask struct {
	Name        string
	Describe    string
	Image       string
	Volumes     []string
	ImageAlias  string
	Command     []string
	LinksTo     string
	Async       bool
	Entrypoint  []string
	Concurrency int
	Duration    time.Duration
	LogLevel    int
	LogDir      string
	CIDs        []string
}

type TaskResult struct {
	ID      string
	Image   string
	Command []string
	Error   error
}

func (cm *ContainerManager) NewContainerOptions(image string, cmd []string, binds []string) docker.CreateContainerOptions {

	hostConfig := docker.HostConfig{
		Binds: binds,
	}

	config := docker.Config{
		Image: image,
		Cmd:   cmd,
	}

	options := docker.CreateContainerOptions{
		Config:     &config,
		HostConfig: &hostConfig,
	}
	return options
}

func (t *ContainerTask) UpdateContainerOptions(options *docker.CreateContainerOptions) {

	if len(t.LinksTo) > 0 {
		options.HostConfig.Links = GenerateLinkPairs(t.LinksTo)
	}

	if len(t.Entrypoint) > 0 {
		options.Config.Entrypoint = t.Entrypoint
	}

	if t.Name != "" {
		options.Name = t.Name
	}

}

func (cm *ContainerManager) NewServiceOptions(image string, cmd []string) docker.CreateServiceOptions {

	// makes generic service options
	serviceName := RandStr(8)
	containerSpec := swarm.ContainerSpec{
		Image: image,
		Args:  cmd,
	}

	annotations := swarm.Annotations{Name: serviceName}
	policy := swarm.RestartPolicy{Condition: swarm.RestartPolicyConditionNone}
	placement := swarm.Placement{Constraints: []string{"node.labels.zone == client"}}
	taskSpec := swarm.TaskSpec{ContainerSpec: &containerSpec,
		RestartPolicy: &policy,
		Placement:     &placement}

	// service spec requires port config to be placed on swarm nework
	portConfig := []swarm.PortConfig{swarm.PortConfig{}}
	endpointSpec := swarm.EndpointSpec{Ports: portConfig}

	// create service spec
	spec := swarm.ServiceSpec{
		Annotations:  annotations,
		TaskTemplate: taskSpec,
		EndpointSpec: &endpointSpec,
	}

	// create options
	opts := docker.CreateServiceOptions{
		ServiceSpec: spec,
	}

	return opts
}

func (t *ContainerTask) UpdateServiceOptions(options *docker.CreateServiceOptions) {

	// override the generic service options
	if t.Name != "" {
		taskName := strings.Replace(t.Name, ".", "-", -1)
		options.ServiceSpec.Annotations.Name = taskName
	}

	if len(t.LinksTo) > 0 {
		envStr := fmt.Sprintf("SWARM_HOSTS=%s", t.LinksTo)
		options.TaskTemplate.ContainerSpec.Env = []string{envStr}
	}

	// note the inconsistencies between entrypoint and command
	// https://github.com/docker/docker/issues/24196
	if len(t.Entrypoint) > 0 {
		options.TaskTemplate.ContainerSpec.Command = t.Entrypoint
	}

}

type ContainerManager struct {
	Client               *docker.Client
	Endpoint             string
	Network              string
	TagId                map[string]string
	IDs                  []string
	Services             []string
	TapHandle            *tap.T
	ProviderType         string
	SwarmClients         []*docker.Client
	ContainerClientCache cmap.ConcurrentMap
	imageStatus          map[string]string
}

func NewDockerClient(clientUrl string) *docker.Client {
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

	return client
}

func NewContainerManager(clientUrl, provider string, network string) *ContainerManager {

	var client *docker.Client = NewDockerClient(clientUrl)

	cm := ContainerManager{
		Client:               client,
		Endpoint:             clientUrl,
		Network:              network,
		TagId:                make(map[string]string),
		IDs:                  []string{},
		Services:             []string{},
		TapHandle:            tap.New("results.tap4j"),
		ProviderType:         provider,
		SwarmClients:         []*docker.Client{},
		ContainerClientCache: cmap.New(),
		imageStatus:          make(map[string]string),
	}

	// get all swarm nodes
	opts := docker.ListNodesOptions{}
	nodes, _ := client.ListNodes(opts)

	if len(nodes) > 0 { // this is a swarm
		cm.SwarmClients = cm.CreateSwarmClients(clientUrl)
		cm.ProviderType = "swarm"
	}
	return &cm
}

// CreateNetwork will create a docker network that containers
// can be attached to. Each container on a network will be able to
// see other containers on that network. It can be used as an alternative
// to Links.
func (cm *ContainerManager) CreateNetwork(name string) {
	colorsay(fmt.Sprintf("Creating network: %s", name))
	networkOpts := docker.CreateNetworkOptions{
		Name:           name,
		CheckDuplicate: true,
	}
	_, err := cm.Client.CreateNetwork(networkOpts)
	chkerr(err)
}

// AddContainerToNetwork add connected a container to the network specified
// at runtime and set in the provider
func (cm *ContainerManager) AddContainerToNetwork(container *docker.Container) {
	colorsay(fmt.Sprintf("Adding %s -> network %s", container.ID, cm.Network))
	connectNetworkOptions := docker.NetworkConnectionOptions{
		Container: container.ID,
	}
	err := cm.Client.ConnectNetwork(cm.Network, connectNetworkOptions)
	chkerr(err)
}

func (cm *ContainerManager) CreateSwarmClients(clientUrl string) []*docker.Client {

	clients := []*docker.Client{cm.Client}

	// get all swarm nodes
	opts := docker.ListNodesOptions{}
	nodes, err := cm.Client.ListNodes(opts)

	logerr(err)
	for _, n := range nodes {
		status := n.ManagerStatus
		if status != nil {
			if status.Leader == true {
				continue // leader is already added
			}
			if status.Reachability == swarm.ReachabilityReachable {
				addr := strings.Split(status.Addr, ":")[0]
				hostname := n.Description.Hostname
				endpointUrl, _ := url.Parse(cm.Endpoint)
				if endpointUrl.Scheme == "" {
					// parse again with scheme
					endpointUrl, _ = url.Parse("http://" + cm.Endpoint)
				}
				clientParts := strings.Split(endpointUrl.Host, ":")
				port := ""
				if len(clientParts) == 2 {
					port = fmt.Sprintf(":%s", clientParts[1])
				}

				// override cert paths if https
				scheme := endpointUrl.Scheme
				if scheme == "https" {
					// update cert path to reflect hostname
					path := os.Getenv("DOCKER_CERT_PATH")
					pathBase := filepath.Dir(path)
					newPath := filepath.Join(pathBase, hostname)
					os.Setenv("DOCKER_CERT_PATH", newPath)
				}

				// create new client
				swarmClientUrl := fmt.Sprintf("%s://%s%s", scheme, addr, port)
				newClient := NewDockerClient(swarmClientUrl)
				clients = append(clients, newClient)
			}
		}
	}

	return clients
}

func (cm *ContainerManager) AllClients() []*docker.Client {
	clients := []*docker.Client{cm.Client}

	if cm.ProviderType == "swarm" {
		clients = cm.SwarmClients
	}
	return clients
}

func (cm *ContainerManager) NumClients() int {
	return len(cm.AllClients())
}

func (cm *ContainerManager) GetAllContainers() []docker.APIContainers {

	allContainers := []docker.APIContainers{}
	clients := cm.AllClients()

	for _, client := range clients {

		opts := docker.ListContainersOptions{All: true}
		containers, err := client.ListContainers(opts)
		for _, c := range containers {
			allContainers = append(allContainers, c)
		}
		chkerr(err)
	}

	return allContainers
}

func (cm *ContainerManager) GetAllServices() []swarm.Service {
	opts := docker.ListServicesOptions{}
	services, err := cm.Client.ListServices(opts)
	chkerr(err)

	return services
}

func (cm *ContainerManager) ExecContainer(id string, cmd []string, detach bool) error {
	client := cm.ClientForContainer(id)

	// create the exec session
	createOpts := docker.CreateExecOptions{
		Container:    id,
		AttachStdin:  true,
		AttachStdout: true,
		AttachStderr: true,
		Tty:          true,
		Cmd:          cmd,
	}
	exec, err := client.CreateExec(createOpts)
	chkerr(err)

	// start the exec session
	startOpts := docker.StartExecOptions{
		InputStream:  os.Stdin,
		OutputStream: os.Stdout,
		ErrorStream:  os.Stderr,
		Tty:          true,
		RawTerminal:  true,
		Detach:       detach,
	}
	return client.StartExec(exec.ID, startOpts)
}

func (cm *ContainerManager) RemoveContainer(id string) error {
	client := cm.ClientForContainer(id)
	opts := docker.RemoveContainerOptions{ID: id, RemoveVolumes: true, Force: true}
	return client.RemoveContainer(opts)
}

func (cm *ContainerManager) RemoveService(id string) error {
	opts := docker.RemoveServiceOptions{ID: id}
	return cm.Client.RemoveService(opts)
}

func (cm *ContainerManager) KillContainer(id string) error {

	client := cm.ClientForContainer(id)
	c, err := client.InspectContainer(id)
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
		colorsay("remove " + c.Names[0])
	}
}

func (cm *ContainerManager) RemoveAllServices() {
	manager := cm.Client
	// teardown services
	for _, client := range cm.SwarmClients {
		for _, svc := range cm.GetAllServices() {
			cm.Client = client
			err := cm.RemoveService(svc.ID)
			chkerr(err)
			colorsay("remove service " + svc.ID[:6])
		}
	}
	cm.Client = manager
}
func (cm *ContainerManager) RemoveManagedContainers(soft bool) {

	// teardown managed containers
	for _, id := range cm.IDs {
		if cm.CheckContainerExists(id) == false {
			continue // container was already removed
		}
		if soft == false {
			if err := cm.RemoveContainer(id); err != nil {
				ecolorsay(fmt.Sprintf("error removing %s: %s", id[:6], err))
			} else {
				colorsay("remove " + id[:6])
			}
		} else {
			err := cm.KillContainer(id)
			if err == nil {
				colorsay("kill " + id[:6])
			}
		}
	}

	// clear ids
	cm.IDs = []string{}
}

func (cm *ContainerManager) RemoveManagedServices(soft bool) {

	// teardown managed services
	for _, id := range cm.Services {
		if cm.CheckServiceExists(id) == false {
			continue // service was already removed
		}

		// only remove service if doing hard remove in case will be restarted later
		if soft == false {
			if err := cm.RemoveService(id); err != nil {
				ecolorsay(fmt.Sprintf("error removing service %s: %s", id[:6], err))
			} else {
				colorsay("remove service " + id[:6])
			}
		}
	}

	// clear ids
	cm.Services = []string{}
}
func (cm *ContainerManager) CopyFromContainer(id, archive, fromPath, toPath string) {

	// save logs if not already saved
	f := CreateFile(toPath, archive)
	defer f.Close()
	opts := docker.DownloadFromContainerOptions{
		OutputStream: f,
		Path:         fromPath,
	}
	cm.Client.DownloadFromContainer(id, opts)
}

func (cm *ContainerManager) SaveCouchbaseContainerLogs(logDir string) {
	// save logs if not already saved
	for n, id := range cm.IDs {
		imgName := fmt.Sprintf("couchbase-server-%d", n)
		archive := fmt.Sprintf("%s.tar", cm.ContainerLogFile(imgName, id))
		fromPath := "/opt/couchbase/var/lib/couchbase/logs"
		cm.CopyFromContainer(id, archive, fromPath, logDir)
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

func (cm *ContainerManager) CheckContainerExists(id string) bool {
	client := cm.ClientForContainer(id)
	_, err := client.InspectContainer(id)
	return err == nil
}

func (cm *ContainerManager) CheckServiceExists(id string) bool {
	_, err := cm.Client.InspectService(id)
	return err == nil
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

func (cm *ContainerManager) DidPull(repo string) bool {
	_, exists := cm.imageStatus[repo]
	return exists
}

func (cm *ContainerManager) PullImage(repo string) error {
	msg := UtilTaskMsg("[pull]", repo)
	cm.TapHandle.Ok(true, msg)
	fmt.Println(msg)

	// pull image across all clients
	pullChans := []chan error{}
	clients := cm.AllClients()
	for _, client := range clients {
		ch := make(chan error)
		pullChans = append(pullChans, ch)
		go cm.pullImage(client, repo, ch)
	}

	for _, ch := range pullChans {
		err := <-ch
		if err != nil {
			return err
		}
	}
	return nil
}

func (cm *ContainerManager) pullImage(client *docker.Client, repo string, ch chan error) {

	imgOpts := docker.PullImageOptions{
		Repository: repo,
	}
	err := client.PullImage(imgOpts, docker.AuthConfiguration{})
	ch <- err

	cm.imageStatus[repo] = "y"
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
					// use tag hash as image alias
					cm.TagId[repo] = tagId[:7]
					cm.TagImage(name, tagId[:7])
				}
			}
		}
	}
}

func (cm *ContainerManager) TagImage(repo, tag string) error {
	clients := cm.AllClients()

	for _, client := range clients {
		tagOpts := docker.TagImageOptions{Repo: tag}
		if err := client.TagImage(repo, tagOpts); err != nil {
			return err
		}
	}
	return nil
}

func (cm *ContainerManager) BuildImage(opts docker.BuildImageOptions) error {
	colorsay("building image " + opts.Name)

	clients := cm.AllClients()
	buildChans := []chan error{}
	for _, client := range clients {
		ch := make(chan error)
		buildChans = append(buildChans, ch)
		go cm.buildImage(client, opts, ch)
	}

	for _, ch := range buildChans {
		err := <-ch
		if err != nil {
			return err
		}
	}

	return nil
}

func (cm *ContainerManager) buildImage(client *docker.Client, opts docker.BuildImageOptions, ch chan error) {
	opts.OutputStream = os.Stdout
	err := client.BuildImage(opts)
	ch <- err
}

// get logs as string
func (cm *ContainerManager) GetLogs(ID, tail string) string {
	buf := new(bytes.Buffer)
	logOpts := docker.LogsOptions{
		Container:    ID,
		OutputStream: buf,
		ErrorStream:  os.Stderr,
		Follow:       false,
		Stdout:       true,
		Tail:         tail,
	}
	client := cm.ClientForContainer(ID)
	client.Logs(logOpts)
	return buf.String()
}

// get container status
func (cm *ContainerManager) GetStatus(ID string) (string, error) {
	container, err := cm.Client.InspectContainer(ID)
	if err != nil {
		return "", err
	}
	return container.State.StateString(), nil
}

// logging to file or io
func (cm *ContainerManager) LogContainer(ID string, output io.Writer, follow bool) {

	client := cm.ClientForContainer(ID)
	logOpts := docker.LogsOptions{
		Container:    ID,
		OutputStream: output,
		ErrorStream:  os.Stderr,
		RawTerminal:  true,
		Follow:       follow,
		Stdout:       true,
		Stderr:       true,
	}

	client.Logs(logOpts)
}

func (cm *ContainerManager) WaitContainer(container *docker.Container, c chan TaskResult) {

	// get additional info about container
	client := cm.ClientForContainer(container.ID)
	_c, err := client.InspectContainer(container.ID)
	if err == nil && _c.Config != nil {
		container = _c
	}

	// wait for container
	rc, _ := client.WaitContainer(container.ID)

	// create task result
	tResult := TaskResult{
		ID:      container.ID,
		Image:   container.Config.Image,
		Command: container.Config.Cmd,
		Error:   err,
	}

	if rc != 0 && rc != 137 {
		// log on error
		emsg := fmt.Sprintf("%s%s\n%s\n",
			"\n\nError occurred on container, try:\n",
			"docker logs "+container.ID[:6],
			"docker start "+container.ID[:6])
		ecolorsay(emsg)
		cm.LogContainer(container.ID, os.Stdout, false)
		tResult.Error = errors.New(fmt.Sprintf("%d", rc))
	}

	// remove container log
	c <- tResult
}

func (cm *ContainerManager) ContainerLogFile(image, ID string) string {
	return fmt.Sprintf("%s_%s", ParseSlashString(image), ID[:6])
}

func (cm *ContainerManager) StartContainer(id string, hostConfig *docker.HostConfig) error {
	return cm.Client.StartContainer(id, hostConfig)
}

func (cm *ContainerManager) RunContainer(opts docker.CreateContainerOptions) (chan TaskResult, *docker.Container) {

	container, err := cm.Client.CreateContainer(opts)
	logerr(err)

	c := make(chan TaskResult)

	// start container
	err = cm.StartContainer(container.ID, nil)
	logerr(err)

	// Add to network if network is defined
	if cm.Network != "" {
		cm.AddContainerToNetwork(container)
	}

	go cm.WaitContainer(container, c)

	// save ID
	cm.IDs = append(cm.IDs, container.ID)

	return c, container
}

func (cm *ContainerManager) RunService(opts docker.CreateServiceOptions) *swarm.Service {
	service, err := cm.Client.CreateService(opts)
	logerr(err)

	// save ID
	cm.Services = append(cm.Services, service.ID)
	return service
}

func (cm *ContainerManager) ClientForContainer(ID string) *docker.Client {

	if cm.ProviderType == "swarm" {
		if clientID, ok := cm.ContainerClientCache.Get(ID); ok == true {
			swarmClient := cm.SwarmClients[clientID.(int)]
			return swarmClient
		} else {
			// manual look up
			opts := docker.ListContainersOptions{All: true}
			for cid, client := range cm.SwarmClients {
				containers, err := client.ListContainers(opts)
				logerr(err)
				for _, c := range containers {
					if c.ID == ID {
						cm.ContainerClientCache.Set(ID, cid)
						return client
					}
				}
			}
		}
	}

	return cm.Client
}

func (cm *ContainerManager) ContainerForService(service *swarm.Service) (*docker.APIContainers, *docker.Client) {

	// get all containers (TODO: parallel)
	opts := docker.ListContainersOptions{All: true}
	for cid, client := range cm.SwarmClients {
		containers, err := client.ListContainers(opts)
		logerr(err)
		for _, c := range containers {
			labels := c.Labels
			if svcid, ok := labels["com.docker.swarm.service.id"]; ok == true {
				if svcid == service.ID {
					cm.ContainerClientCache.Set(c.ID, cid)
					return &c, client
				}
			}
		}
	}

	return nil, nil
}

func (cm *ContainerManager) RunContainerAsService(opts docker.CreateServiceOptions, wait int) (chan TaskResult, *docker.Container, string) {

	var container *docker.Container
	service := cm.RunService(opts)
	var err error

	// wait for a container for service to be started
	for wait > 0 {
		if c, client := cm.ContainerForService(service); c != nil {
			container, err = client.InspectContainer(c.ID)
			logerr(err)
			break
		} else {
			// not started yet
			time.Sleep(time.Second * 1)
			wait -= 1
		}
	}

	if container == nil {
		err = errors.New("timed out waiting for container services to start")
		logerr(err)
	}

	c := make(chan TaskResult)
	go cm.WaitContainer(container, c)
	// save ID
	cm.IDs = append(cm.IDs, container.ID)

	return c, container, service.ID

}

func (cm *ContainerManager) RunContainerTask(task *ContainerTask) (chan TaskResult, *docker.Container) {

	// get task options
	var container *docker.Container
	var ch chan TaskResult
	if cm.ProviderType == "swarm" {
		// run container within service
		options := cm.NewServiceOptions(task.Image, task.Command)
		task.UpdateServiceOptions(&options)
		ch, container, _ = cm.RunContainerAsService(options, 30)
	} else {
		// run container against standalone docker host
		options := cm.NewContainerOptions(task.Image, task.Command, task.Volumes)
		task.UpdateContainerOptions(&options)
		ch, container = cm.RunContainer(options)
	}

	return ch, container
}

func (cm *ContainerManager) Run(task *ContainerTask) (string, chan error) {

	// save image as alias in case it resolves to a
	// commit hash
	task.ImageAlias = task.Image

	// use repo tag if exists
	if tagId, ok := cm.TagId[task.Image]; ok {
		task.ImageAlias = task.Image
		task.Image = tagId
	} else {

		// pull/build container if necessary
		exists := cm.CheckImageExists(task.Image)

		if exists == false {
			err := cm.PullImage(task.Image)
			logerr(err)
		}

	}

	ch, container := cm.RunContainerTask(task)
	idChans := []chan TaskResult{ch}
	containers := []*docker.Container{container}
	task.CIDs = append(task.CIDs, container.ID)
	fmt.Println(MakeTaskMsg(task.ImageAlias, container.ID, task.Command, false))

	// start additional containers with support for concurrency
	if task.Concurrency > 0 {
		for i := 1; i < task.Concurrency; i++ {
			fmt.Println(MakeTaskMsg(task.ImageAlias, container.ID, task.Command, false))
			ch, container := cm.RunContainerTask(task)
			idChans = append(idChans, ch)
			containers = append(containers, container)
			task.CIDs = append(task.CIDs, container.ID)
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
			cm.ContainerLogFile(task.ImageAlias, container.ID))
		go cm.LogContainer(container.ID, f, true)
		defer f.Close()

		// send to stdout
		if task.LogLevel > 1 {
			go cm.LogContainer(container.ID, os.Stdout, true)
		}
	}

	// wait if necessary
	echan := make(chan error, task.Concurrency)
	if task.Async == false {
		cm.HandleResults(&idChans, echan)
	} else {
		go cm.HandleResults(&idChans, echan)
	}

	return container.ID, echan
}

func (cm *ContainerManager) HandleResults(idChans *[]chan TaskResult, echan chan error) {
	for _, ch := range *idChans {
		rc := <-ch
		if rc.Error == nil {
			cm.TapHandle.Ok(true, MakeTaskMsg(rc.Image, rc.ID, rc.Command, false))
		} else {
			cm.TapHandle.Ok(false, MakeTaskMsg(rc.Image, rc.ID, rc.Command, true))
		}
		go func() {
			echan <- rc.Error
		}()
		close(ch)
	}
}

func (cm *ContainerManager) RunRestContainer(cmd []string) (string, string) {
	var rest_container_id string
	rest_container_svc_id := ""
	image := "appropriate/curl"

	if cm.ProviderType == "swarm" {

		// as swarm
		opts := cm.NewServiceOptions(image, cmd)
		ch, _, svcId := cm.RunContainerAsService(opts, 30)
		rc := <-ch
		logerr(rc.Error)
		rest_container_id = rc.ID
		rest_container_svc_id = svcId

	} else {

		// normal docker, no volume mounts
		volumes := []string{}
		options := cm.NewContainerOptions(image, cmd, volumes)
		_, container := cm.RunContainer(options)
		_, err := cm.Client.WaitContainer(container.ID)
		logerr(err)
		rest_container_id = container.ID

	}

	return rest_container_id, rest_container_svc_id
}

func GenerateLinkPairs(linksTo string) []string {
	links := strings.Split(linksTo, ",")
	pairs := []string{}
	for i, name := range links {
		linkName := fmt.Sprintf("container-%d.st.couchbase.com", i)
		pairs = append(pairs, name+":"+linkName)
	}
	return pairs
}

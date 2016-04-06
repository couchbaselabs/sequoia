package sequoia

import ()

type ActionSpec struct {
	Describe string
	Image    string
	Command  string
	Wait     bool
}

type Test struct {
	Actions []ActionSpec
	Cm      *ContainerManager
}

func NewTestSpec(config Config) Test {
	var actions []ActionSpec
	ReadYamlFile(config.Test, &actions)
	cm := NewContainerManager(config.Client)
	return Test{actions, cm}
}

func (t *Test) Run(scope Scope) {

	// setup scope
	scope.TearDown()
	scope.Setup()

	provider := scope.Provider

	// run actions
	for _, action := range t.Actions {

		// resolve command
		command := scope.CompileCommand(action.Command)

		// compile task
		task := ContainerTask{
			Description: action.Describe,
			Image:       action.Image,
			Command:     command,
			Async:       !action.Wait,
		}
		if provider.GetType() == "docker" {
			task.LinksTo = provider.(*DockerProvider).GetLinkPairs()
		}

		// run
		t.Cm.Run(task)
	}

	scope.TearDown()
}

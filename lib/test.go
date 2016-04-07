package sequoia

import (
	"fmt"
	"strings"
)

type ActionSpec struct {
	Describe   string
	Image      string
	Command    string
	Wait       bool
	Entrypoint string
}

type Test struct {
	Actions    []ActionSpec
	Cm         *ContainerManager
	TestConfig Config
}

func NewTestSpec(config Config) Test {
	var actions []ActionSpec
	ReadYamlFile(config.Test, &actions)
	cm := NewContainerManager(config.Client)
	return Test{actions,
		cm,
		config,
	}
}

func (t *Test) Run(scope Scope) {

	// do optional setup
	if t.TestConfig.SkipSetup == false {
		scope.TearDown()
		scope.Setup()
	}

        if t.TestConfig.SkipTest == true {
	  return
	}

	// run at least <repeat> times or forever if -1
	repeat := t.TestConfig.Repeat
	if repeat == -1 {
		// run forever
		for {
			t._run(scope)
		}
	} else {
		repeat++
		for loops := 0; loops < repeat; loops++ {
			t._run(scope)
		}
	}

}

func (t *Test) _run(scope Scope) {

	// run all actions in test
	var lastAction ActionSpec

	for _, action := range t.Actions {

		// resolve command
		command := scope.CompileCommand(action.Command)

		if action.Image == "" {
			// reuse last action
			action.Image = lastAction.Image
		}

		if action.Describe == "" { // use command as describe
			action.Describe = fmt.Sprintf("%s: %s", action.Image, strings.Join(command, " "))
		}

		// compile task
		task := ContainerTask{
			Describe: action.Describe,
			Image:    action.Image,
			Command:  command,
			Async:    !action.Wait,
		}
		if scope.Provider.GetType() == "docker" {
			task.LinksTo = scope.Provider.(*DockerProvider).GetLinkPairs()
		}
		if action.Entrypoint != "" {
			task.Entrypoint = []string{action.Entrypoint}
		}

		// run
		t.Cm.Run(task)

		lastAction = action
	}

	// do optional teardown
	if t.TestConfig.SkipTeardown == false {
		scope.TearDown()
	}
}

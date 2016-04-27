package sequoia

import (
	"fmt"
	"strconv"
	"strings"
)

type Test struct {
	Actions    []ActionSpec
	TestConfig Config
	Cm         *ContainerManager
}

type ActionSpec struct {
	Describe    string
	Image       string
	Command     string
	Wait        bool
	Entrypoint  string
	Requires    string
	Concurrency int
}

func NewTest(config Config, cm *ContainerManager) Test {
	var actions []ActionSpec
	ReadYamlFile(config.Test, &actions)
	return Test{actions,
		config,
		cm,
	}
}

func (t *Test) Run(scope Scope) {

	// do optional setup
	if t.TestConfig.Options.SkipSetup == false {
		scope.TearDown()
		scope.Setup()
	} else if scope.Provider.GetType() != "docker" {
		// non-dynamic IP's need to be extrapolated before test
		scope.Provider.ProvideCouchbaseServers(scope.Spec.Servers)
		scope.InitCli()
	} else {
		// not doing setup but need to get cb versions
		scope.InitCli()
	}

	if t.TestConfig.Options.SkipTest == true {
		return
	}

	// run at least <repeat> times or forever if -1
	repeat := t.TestConfig.Options.Repeat
	loops := 0
	if repeat == -1 {
		// run forever
		for {
			t._run(scope, loops)
			loops++
		}
	} else {
		repeat++
		for loops = 0; loops < repeat; loops++ {
			t._run(scope, loops)
		}
	}

}

func (t *Test) _run(scope Scope, loop int) {

	var lastAction ActionSpec
	scope.Aux = loop

	// run all actions in test
	for _, action := range t.Actions {

		if action.Image == "" {
			// reuse last action image
			action.Image = lastAction.Image

			// reuse last action requires
			if action.Requires == "" {
				action.Requires = lastAction.Requires
			}
		}

		// check action requirements
		if action.Requires != "" {
			ok := ParseTemplate(&scope, action.Requires)
			pass, err := strconv.ParseBool(ok)
			logerr(err)
			if pass == false {
				colorsay("skipping due to requirements: " + action.Requires)
				lastAction = action
				continue
			}
		}

		// resolve command
		command := scope.CompileCommand(action.Command)

		if action.Describe == "" { // use command as describe
			action.Describe = fmt.Sprintf("%s: %s", action.Image, strings.Join(command, " "))
		}

		// compile task
		task := ContainerTask{
			Describe:    action.Describe,
			Image:       action.Image,
			Command:     command,
			Async:       !action.Wait,
			Concurrency: action.Concurrency,
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
	if t.TestConfig.Options.SkipTeardown == false {
		scope.TearDown()
	}
}

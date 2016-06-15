package sequoia

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

type Test struct {
	Actions []ActionSpec
	Flags   TestFlags
	Cm      *ContainerManager
}

type ActionSpec struct {
	Describe    string
	Image       string
	Command     string
	Wait        bool
	Before      string
	Entrypoint  string
	Requires    string
	Concurrency string
	Duration    string
	Save        string
	Repeat      int
	Until       string
}

func ActionsFromFile(fileName string) []ActionSpec {
	var actions []ActionSpec
	ReadYamlFile(fileName, &actions)
	return actions
}

func ActionsFromArgs(image string, command string, wait bool) []ActionSpec {
	action := ActionSpec{
		Image:   image,
		Command: command,
		Wait:    wait,
	}
	return []ActionSpec{action}
}

func NewTest(flags TestFlags, cm *ContainerManager) Test {

	// define test actions from config and flags
	var actions []ActionSpec
	switch flags.Mode {
	case "image":
		actions = ActionsFromArgs(*flags.ImageName, *flags.ImageCommand, *flags.ImageWait)
	default:
		actions = ActionsFromFile(*flags.TestFile)
	}
	return Test{actions, flags, cm}
}

func (t *Test) Run(scope Scope) {

	// do optional setup
	if *t.Flags.SkipSetup == false {
		// if in default mode purge all containers
		if t.Flags.Mode == "" {
			t.Cm.RemoveAllContainers()
		}
		scope.Setup()
	} else if scope.Provider.GetType() != "docker" {
		// non-dynamic IP's need to be extrapolated before test
		scope.Provider.ProvideCouchbaseServers(scope.Spec.Servers)
		scope.InitCli()
	} else {
		// not doing setup but need to get cb versions
		scope.InitCli()
	}

	if *t.Flags.SkipTest == true {
		return
	}

	// run at least <repeat> times or forever if -1
	repeat := *t.Flags.Repeat
	loops := 0
	if repeat == -1 {
		// run forever
		for {
			t.runTest(scope, loops)
			loops++
		}
	} else {
		repeat++
		for loops = 0; loops < repeat; loops++ {
			t.runTest(scope, loops)
		}
	}
	t.Cm.TapHandle.AutoPlan()

	// do optional teardown
	if *t.Flags.SkipTeardown == false {
		scope.TearDown(*t.Flags.SoftTeardown)
	}
}

func (t *Test) runTest(scope Scope, loop int) {

	var lastAction ActionSpec
	scope.Loops = scope.Loops + loop

	// run all actions in test
	for _, action := range t.Actions {

		if action.Image == "" {
			// reuse last action image
			action.Image = lastAction.Image

			// reuse last action requires
			if action.Requires == "" {
				action.Requires = lastAction.Requires
			}
			// reuse last duration
			if action.Duration == "" {
				action.Duration = lastAction.Duration
			}
			// reuse last concurrency
			if action.Concurrency == "" {
				action.Concurrency = lastAction.Concurrency
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

		// resolve duration and concurrency
		var taskDuration time.Duration = 0
		var taskConcurrency = 0
		var err error
		if action.Duration != "" {
			// parse template if units not found
			if strings.Index(action.Duration, "ns") == -1 {
				action.Duration = fmt.Sprintf("%s%s", ParseTemplate(&scope, action.Duration), "ns")
			}
			taskDuration, err = time.ParseDuration(action.Duration)
			logerr(err)
		}
		if action.Concurrency != "" {
			action.Concurrency = ParseTemplate(&scope, action.Concurrency)
			taskConcurrency, err = strconv.Atoi(action.Concurrency)
			logerr(err)
		}

		if action.Describe == "" { // use command as describe
			action.Describe = fmt.Sprintf("start %s: %s", action.Image, strings.Join(command, " "))
		}

		// compile task
		task := ContainerTask{
			Name:        *t.Flags.ContainerName,
			Describe:    action.Describe,
			Image:       action.Image,
			Command:     command,
			Async:       !action.Wait,
			Duration:    taskDuration,
			Concurrency: taskConcurrency,
			LogLevel:    *t.Flags.LogLevel,
			LogDir:      *t.Flags.LogDir,
			CIDs:        []string{},
		}

		if scope.Provider.GetType() == "docker" {
			task.LinksTo = scope.Provider.(*DockerProvider).GetLinkPairs()
		}
		if action.Entrypoint != "" {
			task.Entrypoint = []string{action.Entrypoint}
		}

		// run task
		if task.Async == true {
			go t.runTask(&scope, &task, &action)
		} else {
			t.runTask(&scope, &task, &action)
		}

		lastAction = action
		time.Sleep(5 * time.Second)
	}

	// kill test containers
	scope.Cm.RemoveManagedContainers(false)

}

func (t *Test) runTask(scope *Scope, task *ContainerTask, action *ActionSpec) {

	actionBefore := action.Before
	repeat := action.Repeat
	rChan := make(chan bool) // repeat chan
	uChan := make(chan bool) // until chan

	// generate save key if not specified
	saveKey := action.Save
	if saveKey == "" {
		saveKey = RandStr(6)
	}

	// if command has 'before' then cannot start processing until ready
	if actionBefore != "" {
		var ready = false
		var err error
		for ready == false {
			before := ParseTemplate(scope, actionBefore)
			ready, err = strconv.ParseBool(before)
			logerr(err)
		}
	}

	if action.Command == "" {
		// noop
		return
	}

	if action.Until != "" {
		// start until watcher
		go t.watchTask(scope, task, saveKey, action.Until, uChan)
	}

	// run once
	cid, echan := t.Cm.Run(task)
	scope.SetVarsKV(saveKey, cid)
	go t.WatchErrorChan(echan, task.Concurrency)

	go t.RepeatTask(scope, cid, repeat, rChan)
	if repeat > 0 {
		// waiting on finite number of repeats
		<-rChan
		t.KillTaskContainers(task)
	}

	if action.Until != "" {
		// waiting for until condition satisfied
		<-uChan
		t.KillTaskContainers(task)
	}

}

func (t *Test) WatchErrorChan(echan chan error, n int) {
	if n == 0 {
		n = 1
	}
	for i := 0; i < n; i++ {
		if err := <-echan; err != nil {
			if *t.Flags.StopOnError == true {
				// print test results
				t.Cm.TapHandle.AutoPlan()
				// exit
				os.Exit(1)
			}
		}
	}
	close(echan)
}

func (t *Test) KillTaskContainers(task *ContainerTask) {
	// until removes task containers when reached
	for _, id := range task.CIDs {
		t.Cm.RemoveContainer(id)
	}
}

func (t *Test) RepeatTask(scope *Scope, cid string, repeat int, done chan bool) {
	// run repeat num times
	for repeat != 0 {
		// only start if it stopped
		if status, err := scope.Cm.GetStatus(cid); err == nil {
			if status == "exited" {
				scope.Cm.StartContainer(cid, nil)
				if repeat > 0 {
					repeat--
				}
			}
		} else {
			// container has been removed
			break
		}
		time.Sleep(1 * time.Second)
	}
	done <- true

}

func (t *Test) watchTask(scope *Scope, task *ContainerTask, saveKey string, condition string, done chan bool) {
	var _done bool
	var err error

	// replace instances of self with savekey
	for _done == false {

		id, ok := scope.GetVarsKV(saveKey)
		if ok == true {
			// make sure we have not been killed by 'duration' or 'repeat' conditions
			if _, err := scope.Cm.GetStatus(id); err != nil {
				break
			}
			condition = strings.Replace(condition, "__self__", saveKey, -1)
			rv := ParseTemplate(scope, condition)
			_done, err = strconv.ParseBool(rv)
			logerr(err)
			time.Sleep(1 * time.Second)
		}
	}
	done <- true
}

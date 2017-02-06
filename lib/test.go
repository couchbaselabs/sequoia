package sequoia

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

type Test struct {
	Templates map[string][]ActionSpec
	Actions   []ActionSpec
	Flags     TestFlags
	Cm        *ContainerManager
	CollMgr   *CollectionManager
}

type CollectionManager struct {
	Ch                []chan bool
	ActiveCollections int
}

type ActionSpec struct {
	Describe    string
	Image       string
	Command     string
	Wait        bool
	CondWait    string
	Before      string
	Entrypoint  string
	Requires    string
	Concurrency string
	Duration    string
	Alias       string
	Repeat      int
	Until       string
	Include     string
	Template    string
	Args        string
	Test        string
	Scope       string
	ForEach     string
	Client      ClientActionSpec
}

// returns yaml formattable string
func (a *ActionSpec) String() string {
	return fmt.Sprintf(
		`-
 image: %q
 command: %q
 wait: %t
 condwait: %q
 before: %q
 entrypoint: %q
 requires: %q
 concurrency: %q
 duration: %q
 alias: %q
 repeat: %d
 template: %q
 args: %q
 client: %v
`, a.Image, a.Command, a.Wait, a.CondWait, a.Before, a.Entrypoint, a.Requires,
		a.Concurrency, a.Duration, a.Alias, a.Repeat,
		a.Template, a.Args, a.Client)
}

type TemplateSpec struct {
	Name    string
	Actions []ActionSpec
	ForEach string
}

type ClientActionSpec struct {
	Op        string
	Container string
	FromPath  string
	ToPath    string
}

func (c ClientActionSpec) String() string {

	return fmt.Sprintf(`
    op: %q
    container: %q
    frompath: %q
    topath: %q`,
		c.Op, c.Container,
		c.FromPath, c.ToPath)
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

func ActionsFromString(actionStr string) []ActionSpec {
	var resolvedActions = []ActionSpec{}
	DoUnmarshal([]byte(actionStr), &resolvedActions)
	return resolvedActions
}

func NewTest(flags TestFlags, cm *ContainerManager) Test {

	// define test actions from config and flags
	var templates = make(map[string][]ActionSpec)
	var actions []ActionSpec
	switch flags.Mode {
	case "image", "testrunner":
		actions = ActionsFromArgs(*flags.ImageName, *flags.ImageCommand, *flags.ImageWait)
		if *flags.Exec == true {
			// create new exec action
			clientAction := ClientActionSpec{
				Op:        "exec",
				Container: "testrunner_id",
			}
			execAction := ActionSpec{
				Client: clientAction,
			}

			// don't wait for testrunner to run
			actions[0].Wait = false
			actions[0].Alias = "testrunner_id"

			// add exec action to test
			actions = append(actions, execAction)

			// no extra logging
			*flags.LogLevel = 0
		}
	default:
		actions = ActionsFromFile(*flags.TestFile)
	}

	ch := []chan bool{}
	chmgr := CollectionManager{ch, 0}
	return Test{templates, actions, flags, cm, &chmgr}
}

func (t *Test) Run(scope Scope) {

	// do optional setup
	if *t.Flags.SkipSetup == false {
		// if in default mode purge all containers
		if (t.Flags.Mode == "") && (*t.Flags.SoftCleanup == false) {
			if scope.Provider.GetType() == "swarm" {
				t.Cm.RemoveAllServices()
			} else {
				t.Cm.RemoveAllContainers()
			}
		}
		scope.Provider.ProvideCouchbaseServers(scope.Spec.Servers)
		if t.Flags.Mode == "" {
			scope.Setup()
		}
	} else if (scope.Provider.GetType() != "docker") &&
		(scope.Provider.GetType() != "swarm") {
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
	// run can be terminated if Duration flag set
	repeat := *t.Flags.Repeat
	loops := 0
	duration := *t.Flags.Duration

	if duration > 0 {
		go t.ExitAfterDuration(duration)
		if repeat == 0 {
			repeat = -1 // ensure test runs entire duration
		}
	}

	if repeat == -1 {
		// run forever
		for {
			t.runActions(scope, loops, t.Actions)
			// kill test containers
			t.DoContainerCleanup(scope)

			loops++
		}
	} else {
		repeat++
		for loops = 0; loops < repeat; loops++ {
			t.runActions(scope, loops, t.Actions)
			// kill test containers
			t.DoContainerCleanup(scope)
		}
	}
	t.Cm.TapHandle.AutoPlan()

	// wait if collect is happening
	t.WaitForCollect()

	// do optional cluster teardown
	if *t.Flags.SkipTeardown == false {
		scope.Teardown()
	}

	// do optional cleanup
	if *t.Flags.SkipCleanup == false {
		t.Cleanup(scope)
	}
}

// blocks when item is being collected
func (t *Test) WaitForCollect() {
	for i := 0; i < t.CollMgr.ActiveCollections; i++ {
		colorsay("collect in progress")
		<-t.CollMgr.Ch[i]
	}
}

func (t *Test) runActions(scope Scope, loop int, actions []ActionSpec) {

	var lastAction ActionSpec
	scope.Loops = scope.Loops + loop

	// run all actions in test
	for _, action := range actions {

		if action.ForEach != "" {
			// resolve foreach template (must result in an iterable)
			// create actions with '.' as the output of the range
			rangeActions := t.ResolveSingleRangeActions(scope, action)
			t.runActions(scope, loop, rangeActions)
			continue
		}

		if action.Client.Op != "" {
			key := action.Client.Container

			// is a client op
			switch action.Client.Op {
			case "kill":
				if id, ok := scope.GetVarsKV(key); ok {
					t.Cm.KillContainer(id)
					colorsay("kill" + key)
				} else {
					ecolorsay("no such container alias " + key)
				}
			case "rm":
				if id, ok := scope.GetVarsKV(key); ok {
					t.Cm.RemoveContainer(id)
					colorsay("remove " + key)
				} else {
					ecolorsay("no such container alias " + key)
				}
			case "cp":
				// allow parsing of topath
				action.Client.ToPath = ParseTemplate(&scope, action.Client.ToPath)
				if id, ok := scope.GetVarsKV(key); ok {
					t.Cm.CopyFromContainer(id,
						PathToFilename(action.Client.ToPath),
						action.Client.FromPath,
						PathToDir(action.Client.ToPath))
					msg := fmt.Sprintf("copying files from %s:%s to %s",
						id[:6],
						action.Client.FromPath,
						action.Client.ToPath)
					colorsay(msg)
				} else {
					ecolorsay("no such container alias " + key)
				}
			case "exec":
				// enter into container
				if id, ok := scope.GetVarsKV(key); ok {
					if err := t.Cm.ExecContainer(id); err != nil {
						emsg := fmt.Sprintf("%s [%s] %s",
							"failed to exec into container ",
							id,
							err)
						ecolorsay(emsg)
					} else {
						// we are inside container, make sure it stays that way
						*t.Flags.SkipCleanup = true

						// running exec ends test
						return
					}
				} else {
					ecolorsay("no such container alias " + key)
				}

			}
			continue
		}

		if action.Scope != "" {
			// transform cluster scope
			newSpec := NewScopeSpec(action.Scope)
			scope.Teardown()
			if scope.Provider.GetType() == "docker" {
				for i, s := range newSpec.Servers {
					if i <= len(scope.Spec.Servers) { // same num of clusters
						s.Count -= scope.Spec.Servers[i].Count
						s.InitNodes -= scope.Spec.Servers[i].InitNodes
						if s.Count < 0 {
							s.Count = 0
						}
						if s.InitNodes < 0 {
							s.InitNodes = 0
						}
						offset := newSpec.Servers[i].Count - s.Count
						newSpec.Servers[i].CountOffset = offset
						newSpec.Servers[i].Count = s.Count
						newSpec.Servers[i].InitNodes = s.InitNodes
					}
				}
			}
			scope.Spec = newSpec
			scope.Provider.ProvideCouchbaseServers(scope.Spec.Servers)
			scope.Setup()
		}
		if action.Test != "" {
			// referencing external test
			testActions := ActionsFromFile(action.Test)
			t.Actions = testActions

			// save test options
			setup := t.Flags.SkipSetup
			teardown := t.Flags.SkipTeardown
			cleanup := t.Flags.SkipCleanup

			ok := true
			t.Flags.SkipSetup = &ok
			t.Flags.SkipTeardown = &ok
			t.Flags.SkipCleanup = &ok

			// run test
			t.Run(scope)

			// restore options
			t.Flags.SkipSetup = setup
			t.Flags.SkipTeardown = teardown
			t.Flags.SkipCleanup = cleanup
			continue
		}

		if action.Include != "" {
			for _, includeFile := range strings.Split(action.Include, ",") {
				includeFile = strings.TrimSpace(includeFile)

				// include template file
				var spec []TemplateSpec
				ReadYamlFile(includeFile, &spec)
				t.CacheIncludedTemplate(scope, spec)
			}
			continue
		}

		if action.Template != "" {
			// run template actions
			if templateActions, ok := t.Templates[action.Template]; ok {
				templateActions = t.ResolveTemplateActions(scope, action)
				t.runActions(scope, loop, templateActions)
			} else {
				ecolorsay("WARNING template not found: " + action.Template)
			}
			continue
		}

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
				lastAction = action
				continue
			}
		}

		if action.CondWait != "" {
			ok := ParseTemplate(&scope, action.CondWait)
			ok = strings.TrimSpace(ok)
			if wait, err := strconv.ParseBool(ok); err == nil {
				action.Wait = wait
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

}

func (t *Test) runTask(scope *Scope, task *ContainerTask, action *ActionSpec) {

	actionBefore := action.Before
	repeat := action.Repeat
	rChan := make(chan bool) // repeat chan
	uChan := make(chan bool) // until chan

	// generate alias key if not specified
	aliasKey := action.Alias
	if aliasKey == "" {
		aliasKey = RandStr(6)
	} else {
		// parse alias
		aliasKey = ParseTemplate(scope, aliasKey)
	}

	// if command has 'before' then cannot start processing until ready
	if actionBefore != "" {
		var ready = false
		var err error
		for ready == false {
			before := ParseTemplate(scope, actionBefore)
			ready, err = strconv.ParseBool(before)
			logerr(err)
			time.Sleep(5 * time.Second)
		}
	}

	if action.Command == "" {
		// noop
		return
	}

	if action.Until != "" {
		// start until watcher
		go t.watchTask(scope, task, aliasKey, action.Until, uChan)
	}

	// run once
	cid, echan := t.Cm.Run(task)
	scope.SetVarsKV(aliasKey, cid)
	go t.WatchErrorChan(echan, task.Concurrency, scope)

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

func (t *Test) CacheIncludedTemplate(scope Scope, spec []TemplateSpec) {

	for _, template := range spec {
		if template.ForEach != "" {
			// this template is within a range loop
			// so extrapolate actions
			template.Actions = t.ResolveTemplateRangeActions(scope, template.Actions, template.ForEach)
		}
		t.Templates[template.Name] = template.Actions
	}
}

// resolve args from include and cache for referencing
func (t *Test) ResolveTemplateActions(scope Scope, action ActionSpec) []ActionSpec {

	var resolvedActions = []ActionSpec{}
	var cachedActions = t.Templates[action.Template]

	for _, subAction := range cachedActions {

		// replace generics args ie $1, $2 with test values
		args := ParseTemplate(&scope, action.Args)
		allArgs := strings.Split(args, ",")
		multiArg := false
		lastArg := ""
		argOffset := 0
		for i, arg := range allArgs {
			arg = strings.TrimSpace(arg)
			if strings.Index(arg, "(") != -1 {
				// this is a multi arg string
				// concatentate until we reach ")"
				multiArg = true
				lastArg = strings.Replace(arg, "(", "", 1)
				argOffset++
				continue
			}
			if multiArg == true {
				arg = fmt.Sprintf("%s,%s", lastArg, arg)
				lastArg = arg
				if strings.Index(arg, ")") != -1 {
					// end of multi arg string
					arg = strings.Replace(arg, ")", "", 1)
					multiArg = false
				} else {
					argOffset++
					continue // still building arg
				}
			}

			idx := fmt.Sprintf("$%d", i-argOffset)

			// reformat action to string
			actionStr := fmt.Sprintf("%s", &subAction)

			// replace any magic vars ... ie $0, $1 with args
			actionStr = strings.Replace(actionStr, idx, arg, -1)
			subAction.Until = strings.Replace(subAction.Until, idx, arg, -1)
			subAction.Before = strings.Replace(subAction.Before, idx, arg, -1)
			subAction.Requires = strings.Replace(subAction.Requires, idx, arg, -1)

			// unmarshal string back to action array
			var resolvedActions = []ActionSpec{}
			DoUnmarshal([]byte(actionStr), &resolvedActions)
			resolvedSubAction := resolvedActions[0]

			// restore keys lost during unmarshal
			resolvedSubAction.ForEach = subAction.ForEach
			t.RestoreConditionalValues(subAction, &resolvedSubAction)
			subAction = resolvedSubAction
		}

		// allow inheritance
		if subAction.Wait == false {
			subAction.Wait = action.Wait
		}
		if subAction.Before == "" {
			subAction.Before = action.Before
		}
		if subAction.Requires == "" {
			subAction.Requires = action.Requires
		}
		if subAction.Concurrency == "" {
			subAction.Concurrency = action.Concurrency
		}
		if subAction.Duration == "" {
			subAction.Duration = action.Duration
		}
		if subAction.Alias == "" {
			subAction.Alias = action.Alias
		}
		if subAction.Repeat == 0 {
			subAction.Repeat = action.Repeat
		}
		if subAction.Until == "" {
			subAction.Until = action.Until
		}

		resolvedActions = append(resolvedActions, subAction)
	}

	return resolvedActions
}

func (t *Test) ResolveSingleRangeActions(scope Scope, action ActionSpec) []ActionSpec {
	return t.ResolveTemplateRangeActions(scope, []ActionSpec{action}, action.ForEach)
}

func (t *Test) ResolveTemplateRangeActions(scope Scope, actions []ActionSpec, rangeStr string) []ActionSpec {

	var resolvedActions = []ActionSpec{}

	// begin range templat
	rangeTemplate := rangeStr

	// convert each contextual action spec to a string
	for _, a := range actions {
		actionStr := fmt.Sprintf("%s", &a)

		// append the range template with the action a spec appended
		rangeTemplate = fmt.Sprintf("%s\n%s", rangeTemplate, actionStr)
	}

	// close range template
	rangeTemplate = fmt.Sprintf("%s\n{{end}}", rangeTemplate)

	// compile the range template with nested action spec
	compiledTemplate := ParseTemplate(&scope, rangeTemplate)
	// convert the result from yaml back to action array
	DoUnmarshal([]byte(compiledTemplate), &resolvedActions)

	// restore conditional specs which are not inlcuded in the marshlling
	t.RestoreConditionalValuesRange(actions, &resolvedActions)
	return resolvedActions
}

func (t *Test) RestoreConditionalValuesRange(originalActions []ActionSpec, actions *[]ActionSpec) {

	// when creating templates from a range, certain conditions are removed
	// to prevent the template compiler from operating on them.
	// this method restores them for run time
	step := len(originalActions)
	offset := 0
	for i, a := range originalActions {
		for j, _ := range *actions {
			offset = i + j*step
			if offset < len(*actions) {
				t.RestoreConditionalValues(a, &(*actions)[offset])
			}
		}
	}
}

func (t *Test) RestoreConditionalValues(originalAction ActionSpec, action *ActionSpec) {
	action.Until = originalAction.Until
	action.Before = originalAction.Before
	action.Requires = originalAction.Requires
}

func (t *Test) WatchErrorChan(echan chan error, n int, scope *Scope) {
	if n == 0 {
		n = 1
	}
	for i := 0; i < n; i++ {
		if err := <-echan; err != nil {
			if *t.Flags.CollectOnError == true {

				// add a new collect channel
				ch := make(chan bool)
				t.CollMgr.Ch = append(t.CollMgr.Ch, ch)
				t.CollMgr.ActiveCollections = len(t.CollMgr.Ch)

				// start collect
				t.CollectInfo(*scope)
				ch <- true
			}

			if *t.Flags.StopOnError == true {
				// print test results
				t.Cm.TapHandle.AutoPlan()
				// exit
				os.Exit(0)
			}
		}
	}
	close(echan)
}

func (t *Test) CollectInfo(scope Scope) {

	// disable collect on where when collecting
	oldFlagVal := t.Flags.CollectOnError
	disabledFlagVal := false
	t.Flags.CollectOnError = &disabledFlagVal

	// construst a collect action
	platform := scope.GetPlatform()
	actionStr := fmt.Sprintf(`
-
  include: tests/templates/util.yml
-
  template: cbcollect_all_%s_nodes
  wait: true`, platform)
	actions := ActionsFromString(actionStr)

	// start collection
	t.runActions(scope, 0, actions)
	t.Flags.CollectOnError = oldFlagVal
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

func (t *Test) watchTask(scope *Scope, task *ContainerTask, aliasKey string, condition string, done chan bool) {
	var _done bool
	var err error

	// replace instances of self with savekey
	for _done == false {

		id, ok := scope.GetVarsKV(aliasKey)
		if ok == true {
			// make sure we have not been killed by 'duration' or 'repeat' conditions
			if _, err := scope.Cm.GetStatus(id); err != nil {
				break
			}
			condition = strings.Replace(condition, "__self__", aliasKey, -1)
			rv := ParseTemplate(scope, condition)
			rv = strings.TrimSpace(rv)
			_done, err = strconv.ParseBool(rv)
			logerr(err)
			time.Sleep(1 * time.Second)
		}
	}
	done <- true
}

func (t *Test) ExitAfterDuration(sec int) {
	// wait
	time.Sleep(time.Duration(sec) * time.Second)
	// print test results
	t.Cm.TapHandle.AutoPlan()
	// exit
	os.Exit(0)
}

func (t *Test) DoContainerCleanup(s Scope) {
	if s.Provider.GetType() == "swarm" {
		s.Cm.RemoveManagedServices(*t.Flags.SoftCleanup)
	} else {
		s.Cm.RemoveManagedContainers(*t.Flags.SoftCleanup)
	}
}

func (t *Test) Cleanup(s Scope) {
	soft := *t.Flags.SoftCleanup
	t.DoContainerCleanup(s)
	switch s.Provider.GetType() {
	case "docker":
		// save logs
		if *t.Flags.LogLevel > 0 {
			s.Provider.(*DockerProvider).Cm.SaveCouchbaseContainerLogs(*t.Flags.LogDir)
		}
		s.Provider.(*DockerProvider).Cm.RemoveManagedContainers(soft)
	case "swarm":
		s.Provider.(*SwarmProvider).Cm.RemoveManagedServices(soft)
	}

}

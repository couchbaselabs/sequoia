package sequoia

import (
	"fmt"
	"os"
	"os/exec"
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
	Describe     string
	Image        string
	Command      string
	Volumes      string
	CommandRaw   string
	Wait         bool
	CondWait     string
	Before       string
	Entrypoint   string
	Requires     string
	Concurrency  string
	Duration     string
	Alias        string
	Repeat       int
	Until        string
	Include      string
	Template     string
	Args         string
	Test         string
	Scope        string
	ForEach      string
	Section      string
	SectionStart string `yaml:"section_start"`
	SectionEnd   string `yaml:"section_end"`
	SectionTag   string `yaml:"section_tag"`
	SectionSkip  string `yaml:"section_skip"`
	Client       ClientActionSpec
}

// returns yaml formattable string
func (a *ActionSpec) String() string {
	return fmt.Sprintf(
		`-
 image: %q
 command: %q
 commandraw: %s
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
`, a.Image, a.Command, a.CommandRaw, a.Wait, a.CondWait, a.Before,
		a.Entrypoint, a.Requires,
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
	mode := strings.Split(flags.Mode, ":")[0]
	switch mode {
	case "image":
		actions = ActionsFromArgs(*flags.ImageName, *flags.ImageCommand, *flags.ImageWait)
	case "testrunner", "sdk":
		actions = ActionsFromArgs(*flags.ImageName, *flags.ImageCommand, *flags.ImageWait)
		if *flags.Exec == true {
			// create new exec action
			clientAction := ClientActionSpec{
				Op:        "exec",
				Container: "framework_id",
			}
			execAction := ActionSpec{
				Client: clientAction,
			}

			// don't wait for framework to run
			actions[0].Wait = false
			actions[0].Alias = "framework_id"
			actions[0].Command = "wait"

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
			if (scope.Provider.GetType() == "swarm") || (t.Cm.ProviderType == "swarm") {
				t.Cm.RemoveAllServices()
			} else {
				t.Cm.RemoveAllContainers()
			}
		}

		scope.Provider.ProvideCouchbaseServers(t.Flags.ProviderConfig, scope.Spec.Servers)

		if t.Flags.Mode == "" {
			scope.SetupServer()
		} else { // just wait for resources
			if t.Flags.Exec == nil || *t.Flags.Exec == false {
				scope.WaitForServers()
			}
		}

		scope.SetupMobile()

	} else if (scope.Provider.GetType() != "docker") &&
		(scope.Provider.GetType() != "swarm") {
		//non-dynamic IP's need to be extrapolated before test
		scope.Provider.ProvideCouchbaseServers(t.Flags.ProviderConfig, scope.Spec.Servers)
		scope.Provider.ProvideSyncGateways(scope.Spec.SyncGateways)
		scope.InitCli()
	} else {
		// not doing setup but need to get cb versions
		scope.InitCli()
	}

	if *t.Flags.SkipTest == true {
		return
	}

	// start topology watcher
	if t.Flags.Mode == "" {
		scope.StartTopologyWatcher()
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

	// in exec mode, just run and exit control
	if t.Flags.Exec != nil && *t.Flags.Exec == true {
		t.runActions(scope, loops, t.Actions)
		return
	}

	if repeat == -1 {
		// run forever
		for {
			t.runRepeatableActions(scope, loops, t.Actions)
			// kill test containers
			t.DoContainerCleanup(scope)

			loops++
		}
	} else {
		repeat++
		for loops = 0; loops < repeat; loops++ {
			t.runRepeatableActions(scope, loops, t.Actions)
			// kill test containers
			if *t.Flags.SkipCleanup == false {
				t.DoContainerCleanup(scope)
			}
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

func (t *Test) runRepeatableActions(scope Scope, loop int, actions []ActionSpec) {
	// run actions
	t.runActions(scope, loop, actions)

	// restore the original test actions because runActions has the side-effect
	// of modifying the Actions member for running nested templates, tests, and sections
	t.Actions = actions
    if *t.Flags.ShowTopology == true {
	scope.getClusteInfo()
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
					colorsay("docker exec -it " + id + " bash")
					subProcess := exec.Command("docker", "-H", *t.Flags.Client, "exec", "-it", id, "bash")
					stdin, err := subProcess.StdinPipe()
					logerr(err)
					defer stdin.Close() // the doc says subProcess.Wait will close it, but I'm not sure, so I kept this line

					subProcess.Stdin = os.Stdin
					subProcess.Stdout = os.Stdout
					subProcess.Stderr = os.Stderr

					if err := subProcess.Start(); err != nil {
						emsg := fmt.Sprintf("%s [%s] %s",
							"failed to exec into container ",
							id,
							err)
						ecolorsay(emsg)
					} else {
						// wait for process to quit and cleanup
						subProcess.Wait()
						*t.Flags.SoftCleanup = false // purge debug containers
						t.Cleanup(scope)
						return
					}
				} else {
					ecolorsay("no such container alias " + key)
				}

			}
			continue
		}
		if action.SectionStart != "" ||
			action.SectionEnd != "" ||
			action.SectionTag != "" {
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
			scope.Provider.ProvideCouchbaseServers(t.Flags.ProviderConfig, scope.Spec.Servers)
			scope.SetupServer()
		}
		if action.Test != "" {
			// referencing external test
			testActions := ActionsFromFile(action.Test)

			// filter by section if provided
			var sectionName string
			if action.SectionSkip != "" {
				sectionName = action.SectionSkip
			} else {
				sectionName = action.Section
			}

			excludedActions := []ActionSpec{}
			if sectionName != "" {
				t.Actions = []ActionSpec{}
				isWithinSection := false
				for _, action := range testActions {
					if action.SectionStart == sectionName {
						isWithinSection = true
					}
					if action.SectionEnd == sectionName {
						isWithinSection = false
					}

					// add action if it's within a section or matches tag
					if isWithinSection || (action.SectionTag == sectionName) {
						t.Actions = append(t.Actions, action)
					} else if action.Include != "" {
						// add any includes needed for test actions
						t.Actions = append(t.Actions, action)
					} else {
						excludedActions = append(excludedActions, action)
					}
				}
			} else {
				t.Actions = testActions
			}

			if action.SectionSkip != "" {
				// skipped actions
				t.Actions = excludedActions
			}

			// save test options
			setup := t.Flags.SkipSetup
			teardown := t.Flags.SkipTeardown
			cleanup := t.Flags.SkipCleanup
			duration := t.Flags.Duration
			repeat := t.Flags.Repeat

			ok := true
			zero := 0
			t.Flags.SkipSetup = &ok
			t.Flags.SkipTeardown = &ok
			t.Flags.SkipCleanup = &ok
			t.Flags.Duration = &zero
			t.Flags.Repeat = &action.Repeat

			// run test
			t.Run(scope)

			// restore options
			t.Flags.SkipSetup = setup
			t.Flags.SkipTeardown = teardown
			t.Flags.SkipCleanup = cleanup
			t.Flags.Duration = duration
			t.Flags.Repeat = repeat
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

		// check if action provides args to a template
		if action.Template != "" || action.Args != "" {
			if action.Template == "" {
				// use last template
				if lastAction.Template != "" {
					action.Template = lastAction.Template
				} else {
					ecolorsay("ERROR: cannot provide args without template: " + action.Args)
				}
			}
			// run template actions
			if templateActions, ok := t.Templates[action.Template]; ok {
				templateActions = t.ResolveTemplateActions(scope, action)
				t.runActions(scope, loop, templateActions)
			} else {
				ecolorsay("WARNING template not found: " + action.Template)
			}

			lastAction = action
			continue
		}

		if action.Image == "" {
			if lastAction.Image != "" {
				// reuse last action image
				action.Image = lastAction.Image
			}

			if action.Template == "" && lastAction.Template != "" {
				// reuse last action template
				action.Template = lastAction.Template
			}

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

		// If volumes are supplies, the container will mount them
		// when launching. The format of the volume string should be:
		// "<path-to-container>/folder1:/<path-in-container>/folder1,<path-to-container>/file1:/<path-in-container>/file2"
		// folder1 and file1 must be in the samd
		volumes := []string{}
		if action.Volumes != "" {
			volumes = BuildVolumes(action.Volumes)
		}

		// compile task
		task := ContainerTask{
			Name:        *t.Flags.ContainerName,
			Describe:    action.Describe,
			Volumes:     volumes,
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
		} else if scope.Provider.GetType() == "swarm" {
			task.LinksTo = scope.Provider.(*SwarmProvider).GetLinkPairs()
		}
		if action.Entrypoint != "" {
			task.Entrypoint = []string{action.Entrypoint}
		}

		// pull latest version of container if we haven't already
		if *t.Flags.SkipPull == false &&
			task.Image != "" &&
			!t.Cm.DidPull(task.Image) {
			t.Cm.PullImage(task.Image)
		}

		if *t.Flags.DryRun == false {
			// run task

			if task.Async == true {
				go t.runTask(&scope, &task, &action)
			} else {
				t.runTask(&scope, &task, &action)
			}

			time.Sleep(5 * time.Second)
		} else if len(task.Command) > 1 {
			// just print command output without actually running
			fmt.Println(task.Image,
				fmt.Sprintf("[wait:%t]", action.Wait),
				strings.Join(task.Command, " "))
		}
		lastAction = action
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
			leftParenPos := strings.Index(arg, "(")
			parenIsEscaped := false
			if leftParenPos != -1 {

				if leftParenPos > 0 {
					leadingParenChar := string(arg[leftParenPos-1])
					if leadingParenChar == "\\" {

						// remove the escape from the action
						arg = strings.Replace(arg, "\\", "", 1)

						// skip
						parenIsEscaped = true
					}
				}

				if parenIsEscaped == false {
					// this is a multi arg string
					lastArg = strings.Replace(arg, "(", "", 1)

					if strings.Index(arg, ")") != -1 {
						// but only has single item
						arg = strings.Replace(lastArg, ")", "", 1)
					} else {
						// concatentate until we reach ")"
						multiArg = true
						argOffset++
						continue
					}
				}
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

		// replace cmd with raw string if specified
		if subAction.CommandRaw != "" {
			subAction.Command = subAction.CommandRaw
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

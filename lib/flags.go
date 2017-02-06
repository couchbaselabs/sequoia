package sequoia

import (
	"flag"
	"fmt"
	"os"
	"strings"
)

type TestFlags struct {
	Mode              string
	Args              []string
	Config            *string
	ScopeFile         *string `yaml:"scope"`
	TestFile          *string `yaml:"test"`
	Client            *string
	Provider          *string
	Platform          *string
	ImageName         *string
	ContainerName     *string
	ImageCommand      *string
	ImageWait         *bool
	SkipSetup         *bool `yaml:"skip_setup"`
	SkipTest          *bool `yaml:"skip_test"`
	SkipTeardown      *bool `yaml:"skip_teardown"`
	SkipCleanup       *bool `yaml:"skip_cleanup"`
	SoftCleanup       *bool `yaml:"soft_cleanup"`
	Continue          *bool
	StopOnError       *bool
	CollectOnError    *bool
	Scale             *int
	Repeat            *int
	Duration          *int
	LogDir            *string
	LogLevel          *int
	CleanLogs         *bool
	CleanContainers   *bool
	Override          *string
	Exec              *bool
	DefaultFlagSet    *flag.FlagSet
	ImageFlagSet      *flag.FlagSet
	CleanFlagSet      *flag.FlagSet
	TestrunnerFlagSet *flag.FlagSet
}

// parse top-level args and set test flag parsing mode
func NewTestFlags() TestFlags {

	f := TestFlags{
		Args: os.Args[1:],
	}

	// detect mode
	if len(f.Args) > 0 {
		if strings.Index(f.Args[0], "-") != 0 {
			// is not a flag, thus mode
			f.Mode = f.Args[0]
		}
	}

	// setup flag values
	f.SetFlagVals()

	return f
}

func (f *TestFlags) SetFlagVals() {
	switch f.Mode {

	case "image":
		// image flagset
		f.ImageFlagSet = flag.NewFlagSet("image", flag.ExitOnError)
		f.AddDefaultFlags(f.ImageFlagSet)
		f.AddImageFlags(f.ImageFlagSet)
	case "clean":
		f.ImageFlagSet = flag.NewFlagSet("clean", flag.ExitOnError)
		f.AddCleanFlags(f.CleanFlagSet)
	case "testrunner":
		// testrunner flagset
		f.TestrunnerFlagSet = flag.NewFlagSet("testrunner", flag.ExitOnError)
		f.AddDefaultFlags(f.TestrunnerFlagSet)
		f.AddTestrunnerFlags(f.TestrunnerFlagSet)

		// include image flags and
		f.AddImageFlags(f.TestrunnerFlagSet)

		// override image flags for testrunner mode
		*f.ImageName = "sequoiatools/testrunner"
		*f.ImageWait = true
		*f.LogLevel = 2
		*f.SoftCleanup = true

	default:
		// default cli flags
		f.DefaultFlagSet = flag.NewFlagSet("default", flag.ExitOnError)
		f.AddDefaultFlags(f.DefaultFlagSet)

	}
}

func (f *TestFlags) Parse() {
	switch f.Mode {
	case "image":
		f.ImageFlagSet.Parse(f.Args[1:])
	case "testrunner":
		f.TestrunnerFlagSet.Parse(f.Args[1:])

		// override scope with ini file
		flagArgs := strings.Split(*f.ImageCommand, " ")
		for i, opt := range flagArgs {
			argOffset := i + 1
			if opt == "-i" {
				if len(flagArgs) >= argOffset {
					iniFile := flagArgs[argOffset]
					*f.ScopeFile = fmt.Sprintf("%s/%s", "containers/testrunner/src", iniFile)
				}
			}
		}
	default:
		f.DefaultFlagSet.Parse(f.Args)
	}

	if *f.Config != "" {
		// set flags to config vars
		ReadYamlFile(*f.Config, f)
	}
}

func (f *TestFlags) AddDefaultFlags(fset *flag.FlagSet) {
	// the default flags values
	// when config is provided then
	// values are overriden
	f.Config = fset.String(
		"config",
		"",
		"config file to use")
	f.Client = fset.String(
		"client",
		"unix:///var/run/docker.sock",
		"docker client")
	f.Provider = fset.String(
		"provider",
		"docker",
		"couchbase provider")
	f.Platform = fset.String(
		"platform",
		"linux",
		"couchbase platform <linux, windows>")
	f.ScopeFile = fset.String(
		"scope",
		"tests/simple/scope_small.yml",
		"scope spec filename")
	f.TestFile = fset.String(
		"test", "tests/simple/test_simple.yml",
		"test spec filename")
	f.SkipSetup = fset.Bool(
		"skip_setup",
		false,
		"skip scope setup")
	f.SkipTest = fset.Bool(
		"skip_test",
		false,
		"skip test")
	f.SkipTeardown = fset.Bool(
		"skip_teardown",
		true,
		"skip cluster teardown")
	f.SkipCleanup = fset.Bool(
		"skip_cleanup",
		false,
		"skip container cleanup")
	f.SoftCleanup = fset.Bool(
		"soft_cleanup",
		false,
		"kill containers on cleanup instead of remove")
	f.Continue = fset.Bool(
		"continue",
		false,
		"test is continuing after stopping/exiting")
	f.StopOnError = fset.Bool(
		"stop_on_error",
		false,
		"stop running test when error occurs")
	f.CollectOnError = fset.Bool(
		"collect_on_error",
		false,
		"run cbcollect when error occurs")
	f.Scale = fset.Int(
		"scale",
		1,
		"scale factor")
	f.Repeat = fset.Int(
		"repeat",
		0,
		"times to repeat test")
	f.Duration = fset.Int(
		"duration",
		0,
		"duration of test; repeats test if necessary")
	f.LogLevel = fset.Int(
		"log_level",
		1,
		"log verbosity 0=silent, 1=file, 2=file+stdout")
	f.LogDir = fset.String(
		"log_dir",
		"logs",
		"directory to save log files")
	f.ContainerName = fset.String(
		"container_name", "",
		"name container created from image")
	f.Override = fset.String(
		"override", "",
		"override params, ie servers:local.count=1,servers:remote.count=1")
}

func (f *TestFlags) AddImageFlags(fset *flag.FlagSet) {
	f.ImageName = fset.String(
		"name", "",
		"name of docker image to run")
	f.ImageCommand = fset.String(
		"command", "",
		"command to run in docker image")
	f.ImageWait = fset.Bool("wait", false, "")
}

func (f *TestFlags) AddCleanFlags(fset *flag.FlagSet) {
	f.CleanLogs = fset.Bool(
		"logs", true,
		"remove all logs")
	f.CleanContainers = fset.Bool(
		"containers", true,
		"remove all containers")
	f.LogDir = fset.String(
		"log_dir",
		"logs",
		"directory of log files")
}

func (f *TestFlags) AddTestrunnerFlags(fset *flag.FlagSet) {
	f.Exec = fset.Bool(
		"exec", false,
		"enter into container for debugging")
}

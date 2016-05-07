package sequoia

import (
	"flag"
	"os"
	"strings"
)

type TestFlags struct {
	Mode            string
	Args            []string
	Config          *string
	ScopeFile       *string `yaml:"scope"`
	TestFile        *string `yaml:"test"`
	Client          *string
	Provider        *string
	ImageName       *string
	ImageCommand    *string
	ImageWait       *bool
	SkipSetup       *bool `yaml:"skip_setup"`
	SkipTest        *bool `yaml:"skip_test"`
	SkipTeardown    *bool `yaml:"skip_teardown"`
	Scale           *int
	Repeat          *int
	LogDir          *string
	LogLevel        *int
	CleanLogs       *bool
	CleanContainers *bool
	DefaultFlagSet  *flag.FlagSet
	ImageFlagSet    *flag.FlagSet
	CleanFlagSet    *flag.FlagSet
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
		"https://192.168.99.102:2376",
		"docker client")
	f.Provider = fset.String(
		"provider",
		"docker",
		"couchbase provider")
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
		false,
		"skip container teardown")
	f.Scale = fset.Int(
		"scale",
		1,
		"scale factor")
	f.Repeat = fset.Int(
		"repeat",
		0,
		"times to repeat test")
	f.LogLevel = fset.Int(
		"log_level",
		1,
		"log verbosity 0=silent, 1=file, 2=file+stdout")
	f.LogDir = fset.String(
		"log_dir",
		"logs",
		"directory to save log files")
}

func (f *TestFlags) AddImageFlags(fset *flag.FlagSet) {
	f.ImageName = fset.String(
		"name", "",
		"name of docker image")
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

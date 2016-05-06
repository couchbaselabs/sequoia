package sequoia

import (
	"flag"
	"os"
	"strings"
)

type TestFlags struct {
	Mode           string
	Args           []string
	ScopeFile      *string
	TestFile       *string
	ConfigFile     *string
	ImageName      *string
	ImageCommand   *string
	ImageWait      *bool
	SkipSetup      *bool
	SkipTest       *bool
	SkipTearDown   *bool
	DefaultFlagSet *flag.FlagSet
	ImageFlagSet   *flag.FlagSet
}

// parse top-level args and set test flag parsing mode
func NewTestFlags() TestFlags {
	f := TestFlags{Args: os.Args[1:]}

	if len(f.Args) > 0 {
		if strings.Index(f.Args[0], "-") != 0 {
			// is not a flag, thus mode
			f.Mode = f.Args[0]
		}
	}

	// default cli flags
	f.DefaultFlagSet = flag.NewFlagSet("default", flag.ExitOnError)
	f.AddDefaultFlags(f.DefaultFlagSet)

	// image flagset
	f.ImageFlagSet = flag.NewFlagSet("image", flag.ExitOnError)
	f.AddDefaultFlags(f.ImageFlagSet)
	f.AddImageFlags(f.ImageFlagSet)

	return f
}

func (f *TestFlags) Parse() {

	switch f.Mode {
	case "image":
		f.ImageFlagSet.Parse(f.Args[1:])
	default:
		f.DefaultFlagSet.Parse(f.Args)
	}

}

func (f *TestFlags) AddDefaultFlags(fset *flag.FlagSet) {
	f.ScopeFile = fset.String("scope", "", "scope spec filename")
	f.TestFile = fset.String("test", "", "test spec filename")
	f.ConfigFile = fset.String("config", "config.yml", "test config filename")
	f.SkipSetup = fset.Bool("skip_setup", false, "")
	f.SkipTest = fset.Bool("skip_test", false, "")
	f.SkipTearDown = fset.Bool("skip_teardown", false, "")
}

func (f *TestFlags) AddImageFlags(fset *flag.FlagSet) {
	f.ImageName = fset.String("name", "", "name of docker image")
	f.ImageCommand = fset.String("command", "", "command to run in docker image")
	f.ImageWait = fset.Bool("wait", false, "")
}

func (f *TestFlags) TestActions(testFile string) []ActionSpec {
	// define test actions from config
	var actions []ActionSpec
	switch f.Mode {
	case "image":
		actions = ActionsFromArgs(*f.ImageName, *f.ImageCommand, *f.ImageWait)
	default:
		actions = ActionsFromFile(testFile)
	}
	return actions
}

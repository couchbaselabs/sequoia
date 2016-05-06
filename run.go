package main

import (
	"flag"
	S "github.com/couchbaselabs/sequoia/lib"
)

func main() {

	// default cli flags
	fSetDefault := flag.NewFlagSet("default", flag.ExitOnError)
	scopeFile := fSetDefault.String("scope", "", "scope spec filename")
	testFile := fSetDefault.String("test", "", "test spec filename")
	configFile := fSetDefault.String("config", "config.yml", "test config filename")

	// image flagset
	fSetImage := flag.NewFlagSet("image", flag.ExitOnError)
	imgName := fSetImage.String("name", "", "name of docker image")
	imgCmd := fSetImage.String("command", "", "command to run in docker image")
	imgWait := fSetImage.Bool("wait", false, "")

	// set parsing mode
	flag.Parse()
	args := flag.Args()
	var mode string
	if len(args) > 0 {
		mode = args[0]
	}

	// parse flags
	switch mode {
	case "image":
		scopeFile = fSetImage.String("scope", "", "scope spec filename")
		configFile = fSetImage.String("config", "config.yml", "test config filename")
		fSetImage.Parse(args[1:])
	default:
		fSetDefault.Parse(args)
	}

	// define config
	config := S.NewConfigSpec(configFile, scopeFile, testFile)
	cm := S.NewContainerManager(config.Client)
	scope := S.NewScope(config, cm)

	// define test actions from config
	var actions []S.ActionSpec
	switch mode {
	case "image":
		actions = S.ActionsFromArgs(*imgName, *imgCmd, *imgWait)
	default:
		actions = S.ActionsFromFile(config.Test)
	}

	// run
	test := S.Test{actions, config, cm}
	test.Run(scope)
}

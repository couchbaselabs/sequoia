package main

import (
	S "github.com/couchbaselabs/sequoia/lib"
)

func main() {

	flags := NewTestFlags()

	// parse flags
	flags.Parse()

	// define test
	config := S.NewConfigSpec(flags.ConfigFile, flags.ScopeFile, flags.TestFile)
	cm := S.NewContainerManager(config.Client)
	scope := S.NewScope(config, cm)
	actions := flags.TestActions(config.Test)
	test := S.Test{actions, config, cm}

	// run
	test.Run(scope)
}

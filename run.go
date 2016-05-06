package main

import (
	S "github.com/couchbaselabs/sequoia/lib"
)

func main() {

	flags := S.NewTestFlags()

	// parse flags
	flags.Parse()

	// define test
	config := S.NewConfigSpec(flags.ConfigFile, flags.ScopeFile, flags.TestFile)
	cm := S.NewContainerManager(config.Client)
	scope := S.NewScope(config, cm)
	test := S.NewTest(config, cm, flags)

	// run
	test.Run(scope)
}

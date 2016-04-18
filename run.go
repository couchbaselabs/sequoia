package main

import (
	"flag"
	S "github.com/couchbaselabs/sequoia/lib"
)

func main() {

	// parse cli
	scopeFile := flag.String("scope", "", "scope spec filename")
	testFile := flag.String("test", "", "test spec filename")
	configFile := flag.String("config", "config.yml", "test config filename")
	flag.Parse()

	// parse config
	config := S.NewConfigSpec(configFile, scopeFile, testFile)
	cm := S.NewContainerManager(config.Client)
	scope := S.NewScope(config, cm)
	test := S.NewTest(config, cm)

	// run
	test.Run(scope)
}

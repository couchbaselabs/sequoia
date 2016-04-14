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
	scope := S.NewScope(config)
	test := S.NewTestSpec(config)

	// run
	test.Run(scope)
}

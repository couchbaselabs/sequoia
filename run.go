package main

import (
	"flag"
	S "github.com/couchbaselabs/sequoia/lib"
)

func main() {

	scopeFile := flag.String("scope", "tests/simple/scope_small.yml", "scope spec filename")
	testFile := flag.String("test", "tests/simple/test_simple.yml", "test spec filename")
	configFile := flag.String("config", "config.yml", "test config filename")
	flag.Parse()

	// parse
	config := S.NewConfigSpec(*configFile)
	config.Scope = *scopeFile
	config.Test = *testFile
	scope := S.NewScope(config)
	test := S.NewTestSpec(config)

	// run
	test.Run(scope)
}

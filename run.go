package main

import (
	S "github.com/couchbaselabs/sequoia/lib"
	"os"
)

func main() {

	// parse
	config := S.NewConfigSpec(os.Args[1])
	scope := S.NewScope(config)
	test := S.NewTestSpec(config)

	// run
	test.Run(scope)
}

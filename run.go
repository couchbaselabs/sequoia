package main

import S "github.com/couchbaselabs/sequoia/lib"

func main() {

	// parse
	flags := S.NewTestFlags()
	flags.Parse()

	// configure
	cm := S.NewContainerManager(*flags.Client, *flags.Provider, *flags.Network)
	scope := S.NewScope(flags, cm)
	test := S.NewTest(flags, cm)

	// run
	test.Run(scope)
}

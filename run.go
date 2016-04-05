package main

import (
	"fmt"
	S "github.com/couchbaselabs/sequoia/lib"
	"os"
)

func main() {

	config := S.NewConfigSpec(os.Args[1])
	scope := S.SetupNewScope(config)

	fmt.Println(scope)
	/* todo: run test */
}

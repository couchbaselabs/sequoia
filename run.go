
package main
import (
	S "github.com/couchbaselabs/sequoia/lib"
	"net/http"
	_ "net/http/pprof"
)
func main() {
	// parse
	flags := S.NewTestFlags()
	flags.Parse()
	// configure
	cm := S.NewContainerManager(*flags.Client, *flags.Provider, *flags.Network)
	scope := S.NewScope(flags, cm)
	test := S.NewTest(flags, cm)
    // debug go routine
	go func() {
		http.ListenAndServe(":30000", nil)
	}()
	// run
	test.Run(scope)
}

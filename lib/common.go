package sequoia

import (
	"fmt"
	"strings"
)

func chkerr(err error) {
	if err != nil {
		panic(err)
	}
}

func ExpandName(name string, count uint8) []string {
	var names []string

	if count <= 1 {
		names = []string{name}
	} else {
		names = make([]string, count)
		var i uint8
		for i = 1; i <= count; i++ {
			parts := strings.Split(name, ".")
			fqn := fmt.Sprintf("%s-%d", parts[0], i)
			if len(parts) > 1 {
				parts[0] = fqn
				fqn = strings.Join(parts, ".")
			}
			names[i-1] = fqn
		}
	}
	return names
}

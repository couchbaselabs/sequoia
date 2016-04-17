package sequoia

import (
	"errors"
	"fmt"
	"github.com/fatih/color"
	"gopkg.in/yaml.v2"
	"io/ioutil"
	"log"
	"strings"
)

func chkerr(err error) {
	if err != nil {
		panic(err)
	}
}
func logerr(err error) {
	if err != nil {
		log.Fatalln(err)
	}
}
func logerrstr(err string) {
	logerr(errors.New(err))
}

func colorsay(msg string) {
	fmt.Println(color.CyanString("\u2192 "), color.WhiteString("%s", msg))
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

func ReadYamlFile(filename string, spec interface{}) {
	source, err := ioutil.ReadFile(filename)
	chkerr(err)

	err = yaml.Unmarshal(source, spec)
	chkerr(err)
	fmt.Println(color.CyanString("\u2192 "), color.WhiteString("ok %s", filename))
}

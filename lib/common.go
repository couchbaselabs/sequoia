package sequoia

import (
	"crypto/rand"
	"encoding/base64"
	"errors"
	"fmt"
	"github.com/fatih/color"
	"github.com/go-ini/ini"
	"gopkg.in/yaml.v2"
	"io/ioutil"
	"log"
	"os"
	"regexp"
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

func ReadIniFile(filename string) *ini.File {

	file, err := ini.Load(filename)
	logerr(err)

	return file
}

func CreateFile(dir, filename string) *os.File {
	err := os.MkdirAll(dir, 0777)
	logerr(err)
	logFile := fmt.Sprintf("%s/%s", dir, filename)
	output, err := os.Create(logFile)
	logerr(err)
	return output
}

func ParseSlashString(s string) string {
	_s := strings.Split(s, "/")
	if len(_s) > 1 {
		return _s[1]
	}
	return _s[0]
}

func RandStr(size int) string {
	rb := make([]byte, size)
	_, err := rand.Read(rb)
	logerr(err)
	str := base64.URLEncoding.EncodeToString(rb)
	reg, err := regexp.Compile("[^A-Za-z0-9]+")
	logerr(err)
	return reg.ReplaceAllString(str, "")
}

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
	"time"
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
func ecolorsay(msg string) {
	fmt.Println(color.RedString("\u2192 "), color.WhiteString("%s", msg))
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
	fmt.Println(color.CyanString("\u2192 "), color.WhiteString("parsed %s", filename))
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

func MakeTaskMsg(image, id string, command []string, is_err bool) string {
	ts := TimeStamp()
	cmd := strings.Join(command, " ")
	meta := fmt.Sprintf("[%s, %s:%s]", ts, image, id[:6])
	if is_err == true {
		meta = color.RedString(meta)
	} else {
		meta = color.CyanString(meta)
	}
	return fmt.Sprintf("%s %s", meta, cmd)
}

func UtilTaskMsg(opt, image string) string {
	return fmt.Sprintf("%s %s", color.CyanString(opt),
		image)
}

func TimeStamp() string {
	now := time.Now()
	return now.Format(time.RFC3339)
}

func DDocViewsToJson(ddoc []ViewSpec) string {

	var views string
	var ddocDef string = "<no_views_defined>"
	for _, view := range ddoc {
		viewDef := fmt.Sprintf(`"%s":{"map":"function(doc, meta){ %s }"}`,
			view.View, view.Map)
		if len(views) > 0 {
			views = views + ","
		}
		views = views + viewDef
	}
	if len(views) > 0 {
		ddocDef = fmt.Sprintf(`{"views":{%s}}`, views)
	}
	return ddocDef
}

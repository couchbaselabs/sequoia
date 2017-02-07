package sequoia

import (
	"crypto/rand"
	"encoding/base64"
	"errors"
	"fmt"
	"github.com/fatih/color"
	"github.com/go-ini/ini"
	"gopkg.in/yaml.v2"
	"io"
	"io/ioutil"
	"log"
	"os"
	"path"
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

func ExpandServerName(name string, count, offset uint8) []string {
	if count <= 1 {
		parts := strings.Split(name, ".")
		if len(parts) == 1 {
			name = fmt.Sprintf("%s-1.st.couchbase.com", name)
		}
		return []string{name}
	} else {
		return ExpandName(name, count, offset)
	}
}

func ExpandBucketName(name string, count, offset uint8) []string {
	if count <= 1 {
		return []string{name}
	} else {
		return ExpandName(name, count, offset)
	}
}

func ExpandName(name string, count, offset uint8) []string {
	var names []string

	names = make([]string, count)
	var i uint8
	for i = offset; i < count+offset; i++ {
		parts := strings.Split(name, ".")
		fqn := fmt.Sprintf("%s-%d", parts[0], i)
		if len(parts) > 1 {
			parts[0] = fqn
			fqn = strings.Join(parts, ".")
		}
		names[i-offset] = fqn
	}
	return names
}

func DoUnmarshal(in []byte, out interface{}) {
	err := yaml.Unmarshal(in, out)
	chkerr(err)
}

func ReadYamlFile(filename string, spec interface{}) {
	source, err := ioutil.ReadFile(filename)
	chkerr(err)

	DoUnmarshal(source, spec)
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

func DDocToJson(ddoc DDocSpec) string {

	var views string
	var ddocDef string = "<no_views_defined>"
	for _, view := range ddoc.ViewSpecs {
		mapReduce := fmt.Sprintf(`"map":"function(doc, meta){ %s }"`, view.Map)
		if view.Reduce != "" {
			mapReduce = fmt.Sprintf(`%s, "reduce": "%s"`, mapReduce, view.Reduce)
		}
		viewDef := fmt.Sprintf(`"%s":{%s}`,
			view.Name, mapReduce)
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

func CommaStrToList(str string) []string {
	parts := []string{}
	for _, s := range strings.Split(str, ",") {
		parts = append(parts, strings.TrimSpace(s))
	}
	return parts
}

func PathToFilename(p string) string {
	return path.Base(p)
}

func PathToDir(p string) string {
	return path.Dir(p)
}

func ToCamelCase(s string) string {
	// camelcasing
	s = strings.Replace(s, "_", " ", -1)
	s = strings.Title(s)
	s = strings.Replace(s, " ", "", -1)
	return s
}

// copyFileContents copies the contents of the file named src to the file named
// by dst. The file will be created if it does not already exist. If the
// destination file exists, all it's contents will be replaced by the contents
// of the source file.
// credit: http://stackoverflow.com/questions/21060945/simple-way-to-copy-a-file-in-golang
func CopyFileContents(src, dst string) (err error) {
	in, err := os.Open(src)
	if err != nil {
		return
	}
	defer in.Close()
	out, err := os.Create(dst)
	if err != nil {
		return
	}
	defer func() {
		cerr := out.Close()
		if err == nil {
			err = cerr
		}
	}()
	if _, err = io.Copy(out, in); err != nil {
		return
	}
	err = out.Sync()
	return
}

package sequoia

import (
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/ioutil"
	"log"
	"os"
	"path"
	"path/filepath"
	"reflect"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/fatih/color"
	"github.com/go-ini/ini"
	"gopkg.in/yaml.v2"
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

	opts := ini.LoadOptions{
		AllowShadows:     true,
		AllowBooleanKeys: true,
	}
	file, err := ini.LoadSources(opts, filename)
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

func RandHostStr(size int) string {
	return fmt.Sprintf("%s.%s", RandStr(size), "st.couchbase.com")
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

func StringToJson(data string, v interface{}) error {
	blob := []byte(data)
	err := json.Unmarshal(blob, &v)
	if err != nil {
		fmt.Println("warning using 'json' filter: ", err, blob)
	}
	return err
}

func BuildVolumes(volumes string) []string {
	// If volumes are supplies, the container will mount them
	// when launching. The formate of the volume string should be:
	// "<path-to-container>/folder1:/<path-in-container>/folder1,<path-to-container>/file1:/<path-in-container>/file2"
	// folder1 and file1 must be in the samd
	volumeParts := strings.Split(volumes, ",")

	// Build an absolute path to the mount location assuming we are executing
	// seqouia from the root of the repository
	exPath, err := filepath.Abs(filepath.Dir(os.Args[0]))
	chkerr(err)

	// Prepend the cwd to the volume mount host path
	// if there is not an absolute path defined
	for i, volume := range volumeParts {
		v := strings.TrimSpace(volume)
		if !strings.HasPrefix(v, "/") {
			v = exPath + "/" + v
		}
		colorsay("Mounting :" + v)
		volumeParts[i] = v
	}

	return volumeParts
}

func ApplyFlagOverrides(overrides string, opts interface{}) {
	// Apply overrides from flags to various types

	parts := strings.Split(overrides, ",")
	for _, component := range parts {
		subparts := strings.Split(component, ":")
		if len(subparts) > 2 {
			// rejoin if already had colon
			subparts = []string{subparts[0],
				strings.Join(subparts[1:], ":"),
			}
		}
		if len(subparts) == 2 {
			key := subparts[0]
			vals := subparts[1]

			switch key {

			case "servers":
				scopeSpec, ok := opts.(*ScopeSpec)
				if !ok {
					return
				}
				vals := strings.Split(vals, ".")
				for i, server := range scopeSpec.Servers {
					if server.Name == vals[0] {
						attrs := strings.Split(vals[1], "=")
						_k := ToCamelCase(attrs[0])
						_v := attrs[1]

						// reflect to spec field
						rspec := reflect.ValueOf(&server)
						el := rspec.Elem()
						val := el.FieldByName(_k)
						switch val.Kind() {
						case reflect.Uint8:
							// update fuild as uint
							u, _ := strconv.ParseUint(_v, 10, 8)
							val.SetUint(u)
						case reflect.String:
							// update fuild as string
							val.SetString(_v)
						}
						scopeSpec.Servers[i] = server
					}
				}
			}
		}
	}
}

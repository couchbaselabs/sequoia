package main

import (
	"fmt"
	"github.com/fatih/color"
	"gopkg.in/yaml.v2"
	"io/ioutil"
	"os"
)

type TestConfig struct {
	Client   string
	Scope    string
	Test     string
	Provider string
}

type ActionSpec struct {
	Container string
	Command   string
	Wait      bool
}

type BucketSpec struct {
	Name    string
	Count   uint8
	Ram     uint32
	Replica uint8
	Type    string
}

type ServerSpec struct {
	Name         string
	Count        uint8
	Ram          uint32
	RestUsername string
	RestPassword string
	RestPort     uint16
	InitNodes    uint8
}

type ScopeSpec struct {
	Buckets []BucketSpec
	Servers []ServerSpec
}

func ReadYamlFile(filename string, spec interface{}) {
	source, err := ioutil.ReadFile(filename)
	if err != nil {
		panic(err)
	}
	err = yaml.Unmarshal(source, spec)
	if err != nil {
		panic(err)
	}
	fmt.Println(color.GreenString("\u2713 "), color.WhiteString("ok %s", filename))
}

func main() {
	filename := os.Args[1]
	var config TestConfig
	ReadYamlFile(filename, &config)

	var actions []ActionSpec
	ReadYamlFile(config.Test, &actions)

	var scope ScopeSpec
	ReadYamlFile(config.Scope, &scope)

}

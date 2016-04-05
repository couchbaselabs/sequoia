package sequoia

type ActionSpec struct {
	Container string
	Command   string
	Wait      bool
}

// var actions []S.ActionSpec
// ReadYamlFile(config.Test, &actions)

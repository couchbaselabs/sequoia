module github.com/couchbaselabs/sequoia

go 1.24.0

require (
	github.com/docker/docker v28.5.1+incompatible
	github.com/fatih/color v1.18.0
	github.com/fsouza/go-dockerclient v1.12.2
	github.com/go-ini/ini v1.67.0
	github.com/streamrail/concurrent-map v0.0.0-20160823150647-8bf1e9bacbf6
	github.com/tahmmee/tap.go v0.0.0-20160509213024-29247087ebdf
	gopkg.in/yaml.v2 v2.4.0
)

require (
	github.com/Azure/go-ansiterm v0.0.0-20210617225240-d185dfc1b5a1 // indirect
	github.com/Microsoft/go-winio v0.6.2 // indirect
	github.com/containerd/log v0.1.0 // indirect
	github.com/docker/go-connections v0.4.0 // indirect
	github.com/docker/go-units v0.5.0 // indirect
	github.com/klauspost/compress v1.18.0 // indirect
	github.com/mattn/go-colorable v0.1.13 // indirect
	github.com/mattn/go-isatty v0.0.20 // indirect
	github.com/moby/docker-image-spec v1.3.1 // indirect
	github.com/moby/go-archive v0.1.0 // indirect
	github.com/moby/patternmatcher v0.6.0 // indirect
	github.com/moby/sys/sequential v0.6.0 // indirect
	github.com/moby/sys/user v0.4.0 // indirect
	github.com/moby/sys/userns v0.1.0 // indirect
	github.com/moby/term v0.0.0-20210619224110-3f7ff695adc6 // indirect
	github.com/morikuni/aec v1.0.0 // indirect
	github.com/opencontainers/go-digest v1.0.0 // indirect
	github.com/opencontainers/image-spec v1.1.0-rc2.0.20221005185240-3a7f492d3f1b // indirect
	github.com/sirupsen/logrus v1.9.3 // indirect
	golang.org/x/sys v0.35.0 // indirect
)

replace github.com/docker/docker/api => github.com/moby/moby/api v1.52.0-beta.4

module github.com/couchbaselabs/sequoia

go 1.21.6

require (
    github.com/docker/docker v28.5.1+incompatible
    github.com/fsouza/go-dockerclient v1.12.2
    github.com/fatih/color v1.18.0
    github.com/go-ini/ini v1.67.0
    github.com/streamrail/concurrent-map v0.0.0-20160823150647-8bf1e9bacbf6
    github.com/tahmmee/tap.go v0.0.0-20160509213024-29247087ebdf
    gopkg.in/yaml.v2 v2.4.0
)

replace github.com/docker/docker/api => github.com/moby/moby/api v1.52.0-beta.4


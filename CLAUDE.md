# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Sequoia is a scalable Docker-based testing framework for Couchbase server components. It provisions infrastructure via Docker containers and runs integration tests across various Couchbase services (Analytics, Eventing, FTS, N1QL, Views, XDCR, SDK, Mobile, and more).

## Core Commands

**Build the sequoia binary:**
```bash
go mod tidy
go build -o sequoia
```

**Run a test:**
```bash
./sequoia
```

**Run with custom scope/test:**
```bash
./sequoia -scope tests/simple/scope_medium.yml -test tests/simple/test_views.yml
```

**Run without setup/teardown (against an existing cluster):**
```bash
./sequoia -skip_setup -scope tests/simple/scope_medium.yml -test tests/simple/test_views.yml
```

**Run against remote servers (file provider):**
```bash
./sequoia -provider "file:hosts.json" -skip_setup -test tests/eventing/totoro/test_eventing.yml
```

**Build Docker containers:**
```bash
./build.sh  # builds all framework containers
docker build -t sequoiatools/testrunner containers/testrunner
```

**Run linting:**
```bash
golangci-lint run
```

**Run with Docker network (experimental):**
```bash
./sequoia -scope tests/simple/scope_medium.yml -test tests/simple/test_views.yml --network cbl
```

## Toolchain Requirements

- **Go version:** 1.24.0 (see `go.mod`)
- **Docker:** Required for the default docker provider; ensure daemon is running
- **Linting:** `golangci-lint` — config in `.golangci.yml`
  - Enabled linters: `govet`, `staticcheck`, `errcheck`, `ineffassign`, `unused`, `gocritic`, `misspell`
  - Formatters: `gofmt`, `goimports` (local prefix: `github.com/couchbaselabs/sequoia`)
- **Pre-commit hooks:** `.pre-commit-config.yaml` — install with `pre-commit install`
  - Hooks: `go-fmt`, `go-imports`, `go-vet`, `go-build`, `golangci-lint-full`

## Repo Layout

- `run.go` - CLI entry point (package main, imports from `lib/`)
- `lib/` - Core Go framework (package sequoia)
  - `test.go` - Test runner and action execution
  - `scope.go` - Infrastructure provisioning and configuration
  - `provider.go` - Docker/File/Dev/Swarm provider implementations
  - `spec.go` - YAML spec structures for servers, buckets, users, actions
  - `container.go` - Docker container lifecycle management
  - `rest.go` - REST API client for Couchbase services
  - `template.go` - Template rendering for test YAML
  - `flags.go` - CLI flag definitions
  - `hostserializer.go` - Host serialization to `hosts.json`
  - `common.go` - Shared utilities
- `containers/` - Docker test frameworks
  - `testrunner/` - Python-based test framework (submodule: github.com/couchbase/testrunner)
  - `perfrunner/` - Performance testing framework
  - `couchbase/`, `couchbase-cli/` - Couchbase server and CLI tools
  - `ftsindexmanager/` - FTS and vector search utilities
  - Service-specific: `eventing/`, `analytics/`, `xdcr/`, `sgw/`, `gideon/`, `pillowfight/`, `catapult/`, etc.
- `tests/` - YAML test definitions organized by service
  - `simple/` - Basic examples (`scope_*.yml`, `test_*.yml`, `suite.yml`)
  - `templates/` - Reusable test snippets (`kv.yml`, `n1ql.yml`, `fts.yml`, etc.)
  - Service directories: `analytics/`, `eventing/`, `fts/`, `n1ql/`, `view/`, `xdcr/`, `mobile/`, `2i/`, `integration/`, etc.
- `config.yml` - Default configuration (client endpoint, provider, scope/test defaults)
- `local/` - Local override files (`scope_local.yml`, `test_local.yml`) for dev use
- `build.sh` - Container build script

## Architecture

### Execution Flow

```
run.go (main)
  → Parse flags (lib/flags.go)
  → Create Provider (docker/file/dev)
  → Scope.Setup()    — provision containers, init cluster, create buckets/users/collections
  → Test.Run(scope)  — iterate ActionSpec list, launch containers per action
  → Scope.Teardown() — remove containers
```

### Scope vs Test

**Scope** (`scope_*.yml`) defines infrastructure: servers, buckets, users, sync gateways. `lib/scope.go` runs a fixed pipeline: wait for nodes → init CLI → init nodes → init cluster → add users → add nodes → rebalance → create buckets → create scopes/collections → create views.

**Test** (`test_*.yml`) defines actions: each action is a Docker container invocation. `lib/test.go` compiles each `ActionSpec` into a container run command using Go templates, then executes it.

Suites (`suite.yml`) combine multiple scope+test pairs for batch runs.

### Provider Selection

| Provider | How to invoke | Behaviour |
|----------|---------------|-----------|
| `docker` | `-provider docker` (default) | Spins up containers via Docker daemon |
| `docker:options.yml` | `-provider docker:options.yml` | Docker with cpu/memory/build overrides |
| `swarm` | `-provider swarm` | Docker Swarm services |
| `file:hosts.json` | `-provider file:hosts.json` | Pre-existing servers, no provisioning |
| `dev:127.0.0.1` | `-provider dev:127.0.0.1` | Local cluster-run (ports 9000, 9500…) |

### ActionSpec — Core Test Unit

Every entry in a test YAML is an `ActionSpec`:

```yaml
- image: sequoiatools/pillowfight          # Docker image to run
  command: "-U {{.Orchestrator}} ..."      # Command (Go template)
  wait: true                               # Block until container exits
  async: true                              # Fire-and-forget
  duration: 60                             # Kill after N seconds
  concurrency: 4                           # Max simultaneous containers
  repeat: -1                               # Loop count (-1 = forever)
  until: "{{.DoOnce}}"                     # Stop looping when condition true
  before: "{{gt .Version 7.0}}"            # Wait for condition before starting
  requires: "{{.DoOnce}}"                  # Skip action if condition false
  alias: my_container                      # Store container ID in scope.Vars
  section_start: rebalance                 # Mark filterable section
  section_end: rebalance
```

**Client operations** (against an already-running container):
```yaml
- client:
    op: exec                               # exec | cp | kill | rm
    container: "{{.Vars.my_container}}"
    command: "bash -c 'echo done'"
```

### Template System (`lib/template.go`)

All `command:` values are Go templates evaluated at runtime against the current `ScopeSpec`:

```
{{.Orchestrator}}               # First server address
{{.Bucket}}                     # First bucket name
{{.NthBucket 1}}                # Second bucket (0-indexed)
{{.Buckets}}                    # Comma-separated bucket list
{{.Scale 1000}}                 # 1000 × -scale flag value
{{.Version}}                    # Server version as float
{{.DoOnce}}                     # True on first loop iteration
{{.Loop}}                       # Current loop number
{{.Nodes}}                      # All ServerSpec objects
{{.Nodes | .Service "index"}}   # Filter nodes by service
{{.InActiveNode}}               # First node not yet in cluster
{{.ActiveDataNode 0}}           # Nth active data node
{{.EventingNode}}               # First eventing node
{{net .NodeAddresses .Nodes 0}} # IP of first node
{{noport "host:port"}}          # Strip port suffix
{{.RestUsername}}, {{.RestPassword}}
{{.AuthUser}}, {{.AuthPassword}}
```

**Template reuse:**
```yaml
- include: tests/templates/kv.yml     # Load template file into cache
- template: kv                         # Reference by name
  args: "{{.Orchestrator}},{{.Bucket}},1000"  # $0, $1, $2 positional args
```

### Scope YAML Reference

```yaml
servers:
  - name: cb
    count: 3
    ram: "60%"                         # % or MB
    services:
      index: 1
      query: 1
      fts: 1
      eventing: 1
      analytics: 1
    buckets: default,beer-sample       # Assign buckets to this cluster

buckets:
  - name: default
    ram: "75%"
    replica: 1
    type: couchbase                    # couchbase | memcached
    storage: couchbase                 # couchbase | magma
    durability: none                   # none | majority | majorityAndPersist | persistToMajority
    bucket_scope_spec:
      - name: myscope
        collections: col1,col2

users:
  - name: Administrator
    password: password
    roles: admin
    auth_domain: builtin               # builtin | external
```

### Config File (`config.yml`)

Sets defaults for all flags; any value can be overridden on the CLI:

```yaml
client: "unix:///var/run/docker.sock"
scope: tests/simple/scope_small.yml
test: tests/simple/test_simple.yml
provider: docker
scale: 1
skip_setup: false
skip_teardown: false
repeat: 0
```

### Outputs

- `logs/` — per-action log files and `results.tap4j` (TAP format)
- `hosts.json` — generated host map (consumed by file provider)
- `report.xml` — generated when `-generate_xml` flag is set

## Validation Before Completion

**Code changes:**
- Go: `go build -o sequoia` must succeed
- Linting: `golangci-lint run` must pass
- Docker containers: verify with `docker build` or `./build.sh`
- Test YAML: validate syntax and spec structure

**Runtime verification:**
- Run `./sequoia` to confirm end-to-end provisioning and cleanup
- Check `logs/` for test results and debug output

## Security and Sensitive Paths

- Test files contain default credentials (`password: password`, `rest_username: Administrator`) — expected, do not replace with production credentials
- Docker client endpoint can expose the daemon if TLS is misconfigured
- `hosts.json` and `logs/` are generated at runtime; `.gitignore` already covers them
- File provider pointing at remote servers may require VPN access

## Supporting Docs

- [Repo Inventory](docs/agent-context/repo-inventory.md) - Languages, tools, directories, and build commands
- [Build/Test Matrix](docs/agent-context/build-test-matrix.md) - Build and validation commands by component
- [Domain Glossary](docs/agent-context/domain-glossary.md) - Couchbase services, framework terms, and test environments
- [Troubleshooting](docs/agent-context/troubleshooting.md) - Common issues, log locations, and recovery steps
- [Architecture](docs/architecture.agents.md) - System flows, provider patterns, and component boundaries

## Unknowns

- No Go unit test files in the repo (integration tests only, via Docker containers)
- No CI/CD pipelines detected (no .github/, .gitlab-ci.yml, etc.)
- Documentation wiki referenced (Test Syntax, Providers) exists externally, not in this repo
- Specific version compatibility matrix for Couchbase releases not documented locally

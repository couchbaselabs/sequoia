# Repo Inventory - Sequoia

## Languages

- **Go** (primary framework)
  - Version: 1.21.6 (from go.mod)
  - Location: `lib/` (core framework), `run.go` (entry point)
  - Dependencies: Docker client API, YAML parsing, HTTP/REST
  - No unit tests found in the repo

- **Python 3.7+/Python 2.7**
  - Used in: `containers/testrunner/` (submodule: github.com/couchbase/testrunner)
  - Purpose: Python-based test execution framework
  - Dependencies: couchbase SDK, paramiko, httplib2, pyyaml, requests, docker

- **YAML**
  - Test scope definitions: `tests/*/scope_*.yml`
  - Test action definitions: `tests/*/test_*.yml`
  - Configuration: `config.yml`

## Package and Build Tools

- **Go Modules**: `go.mod`
  - Build command: `go build -o sequoia`
  - Dependency management: `go mod tidy`

- **Docker**: Container-based testing infrastructure
  - Used for both framework and test execution
  - Base images: ubuntu, centos, custom Couchbase builds

- **Shell Scripts**: `build.sh`
  - Orchestrates container builds
  - Accepts BUILD_NO argument for versioning

- **npm** (mentioned in build.sh)
  - Purpose: Unknown (npm install called but no package.json found)

## Key Directories

### Core Framework
- `lib/` - Go test framework source
  - `run.go` - Main entry point
  - `test.go` - Test runner
  - `scope.go` - Infrastructure provisioning
  - `provider.go` - Docker/file/dev providers
  - `spec.go` - YAML spec definitions
  - `container.go` - Container management
  - `rest.go` - Couchbase REST API client
  - `flags.go` - CLI argument parsing
  - `template.go` - Template processing
  - `common.go` - Shared utilities

### Test Definitions
- `tests/` - YAML test suites organized by service
  - `simple/` - Basic examples and demos
  - `templates/` - Reusable test sections
  - `integration/` - Full-stack integration tests
  - Service-specific: `analytics/`, `eventing/`, `fts/`, `n1ql/`, `view/`, `xdcr/`, `mobile/`, `2i/`, `sgw/`, `rebalance/`, `ycsb/`, `backuprestore/`, `sdk/`

### Docker Containers
- `containers/` - Test framework containers
  - `testrunner/` - Python test framework (git submodule)
  - `perfrunner/` - Performance testing
  - `couchbase/` - Couchbase server builds
  - `couchbase-cli/` - CLI tools (version-specific directories)
  - `ftsindexmanager/` - FTS utilities (Go vector loader, Python synonym loader)
  - Service containers: `eventing/`, `analytics/`, `xdcr/`, `pillowfight/`, `gideon/`, `catapult/`, `tpcc/`, `ycsb`, `sgw/`, `query_manager/`, `vegeta/`, etc.
  - `templates/` - Base image templates (ubuntu-gcc, ubuntu-python, ubuntu-vbr)

### Generated/Config
- `logs/` - Test execution results (results.tap4j, debug logs)
- `local/` - Local test configurations
- `config.yml` - Default configuration

## Test Entry Points

**Main CLI:**
```bash
./sequoia                    # Run default test from config.yml
./sequoia -scope <file> -test <file>  # Run specific test
./sequoia --network <name>   # Use Docker network
```

**Build Commands:**
```bash
go build -o sequoia          # Build Go binary
./build.sh [BUILD_NO]        # Build all containers
docker build -t <name> <dir> # Build specific container
```

**Test Execution:**
- Sequoia orchestrates tests via Docker containers
- Testrunner (Python) executes Python-based tests
- Individual service containers run service-specific workloads

## Important Configurations

- `config.yml` -
  - `client`: Docker endpoint (unix:///var/run/docker.sock, http://host:2375, https://host:2376)
  - `provider`: docker, file, or dev
  - `scope/test`: Default test files
  - `scale`: Workload scaling factor
  - Network, repeat, skip_setup/skip_teardown flags

## Unknowns

- **npm purpose**: build.sh calls `npm install` but no package.json found
- **Go unit tests**: No test files found (*_test.go)
- **CI/CD**: No GitHub Actions, GitLab CI, or Jenkins configurations detected
- **Linting**: No golangci-lint, gofmt, or other linter configs
- **Code coverage**: No coverage tools or reports
- **Version compatibility**: No documented matrix of Couchbase version support
- **Testrunner submodule**: No version pinning in .gitmodules (master HEAD)
- **Documentation**: Wiki referenced but not local (Test Syntax, Providers docs external)

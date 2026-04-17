# AGENTS.md

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

**Build Docker containers:**
```bash
./build.sh  # builds all framework containers
```

**Build specific container:**
```bash
docker build -t sequoiatools/testrunner containers/testrunner
```

**Run with Docker network (experimental):**
```bash
./sequoia -scope tests/simple/scope_medium.yml -test tests/simple/test_views.yml --network cbl
```

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
  - `ftsindexmanager/` - FTS and vector search utilities (Go and Python loaders)
  - Service-specific containers: `eventing/`, `analytics/`, `xdcr/`, `sgw/`, `gideon/`, `pillowfight/`, `catapult/`, etc.
- `tests/` - YAML test definitions organized by service
  - `simple/` - Basic examples (scope_*.yml, test_*.yml, suite.yml)
  - `templates/` - Reusable test snippets (kv.yml, n1ql.yml, fts.yml, etc.)
  - Service directories: `analytics/`, `eventing/`, `fts/`, `n1ql/`, `view/`, `xdcr/`, `mobile/`, `2i/`, `integration/`, etc.
- `config.yml` - Default configuration (client endpoint, provider, scope/test defaults)
- `local/` - Local override files (`scope_local.yml`, `test_local.yml`) for dev use
- `build.sh` - Container build script

## Development Patterns and Constraints

**Configuration:**
- Use YAML files for infrastructure (`scope_*.yml`) and test actions (`test_*.yml`)
- `config.yml` defines provider type (docker/file/dev) and Docker client endpoint
- Support for multiple providers: docker (default), file (remote servers), dev (cluster-run)

**Test Structure:**
- Scope files define infrastructure (servers, buckets, users, sync gateways, clusters)
- Test files define actions to run against the infrastructure
- Templates allow reusable test sections (e.g., `kv.yml` for common KV operations)
- Suites combine multiple tests with their scopes

**Provider Selection:**
- Docker provider spins up containers dynamically
- File provider connects to pre-existing remote servers
- Swarm provider for Docker Swarm environments

**Scaling:**
- `scale` parameter in config.yml (default: 1) multiplies workload sizes
- Support for concurrent test execution and collection iteration

**Container Management:**
- Containers can be started with `wait: true` to block until ready
- Support for conditional waits, retries, and duration-based tests
- Automatic cleanup via `skip_teardown` flag

## Toolchain Requirements

- **Go version:** 1.24.0 (see `go.mod`)
- **Docker:** Required for the default docker provider; ensure daemon is running
- **Linting:** `golangci-lint` — config in `.golangci.yml`
  - Enabled linters: `govet`, `staticcheck`, `errcheck`, `ineffassign`, `unused`, `gocritic`, `misspell`
  - Formatters: `gofmt`, `goimports` (local prefix: `github.com/couchbaselabs/sequoia`)
  - Run: `golangci-lint run`
- **Pre-commit hooks:** `.pre-commit-config.yaml` — install with `pre-commit install`

## Validation and Evidence Required Before Completion

**Code Changes:**
- Go code: Ensure `go build -o sequoia` succeeds without errors
- Linting: Run `golangci-lint run` and resolve any reported issues
- Docker containers: Verify container builds with `docker build` or `./build.sh`
- Test YAML: Validate YAML syntax and spec structure

**Testing:**
- Run a simple test: `./sequoia` should complete successfully
- Verify container provisioning and cleanup work correctly
- Check logs in `logs/` directory for test results and debug output

**Security:**
- Review Docker client endpoint configuration (ensure proper TLS certs for HTTPS)
- Check for hardcoded credentials in test files (passwords, API keys)
- Verify no sensitive data in `hosts.json`, `.gitignore` covers generated files

## Security and Sensitive Path Guidance

**Credentials:**
- Test files often contain default credentials (e.g., `password: password`, `rest_username: Administrator`)
- Docker client endpoints may expose container daemon if misconfigured
- Avoid committing production credentials or API keys

**Generated Files:**
- `logs/` - Test execution logs and results.tap4j
- `hosts.json` - Generated host mappings during tests
- `.idea/` - IDE config (already gitignored)

**Network Access:**
- Docker provider requires access to Docker daemon (check TLS configuration)
- Remote servers (file provider) may need VPN/proxy access

**Resource Usage:**
- Tests can spawn multiple containers; check disk space and memory limits
- Long-running tests may accumulate resources if cleanup fails

## Links to Supporting Docs

- [Repo Inventory](docs/agent-context/repo-inventory.md) - Languages, tools, directories, and build commands
- [Build/Test Matrix](docs/agent-context/build-test-matrix.md) - Build and validation commands by component
- [Domain Glossary](docs/agent-context/domain-glossary.md) - Couchbase services, framework terms, and test environments
- [Troubleshooting](docs/agent-context/troubleshooting.md) - Common issues, log locations, and recovery steps
- [Architecture](docs/architecture.agents.md) - System flows, provider patterns, and component boundaries

## Unknowns

- No Go unit test files in the repo (integration tests only, via Docker)
- No CI/CD pipelines detected (no .github/, .gitlab-ci.yml, etc.)
- Documentation wiki referenced (Test Syntax, Providers) exists externally, not in this repo
- Specific version compatibility matrix for Couchbase releases not documented locally

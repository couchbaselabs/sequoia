# Build Test Matrix - Sequoia

## Build Commands

### Go Framework
```bash
# Initialize/update dependencies
go mod init
go mod tidy

# Build the main binary
go build -o sequoia

# Run the binary
./sequoia
```

### Docker Containers
```bash
# Build all framework containers
./build.sh [BUILD_NO]

# Build specific container
docker build -t sequoiatools/testrunner containers/testrunner
docker build -t sequoiatools/perfrunner containers/perfrunner
docker build --build-arg BUILD_NO=<build_no> -t couchbase-watson containers/couchbase

# Build base templates
docker build -t ubuntu_gcc -f containers/templates/Dockerfile-ubuntu-gcc containers/templates/
docker build -t ubuntu_python -f containers/templates/Dockerfile-ubuntu-python containers/templates/
docker build -t ubuntu_vbr -f containers/templates/Dockerfile-ubuntu-vbr containers/templates/

# Pull public images
docker pull martin/wait
docker pull clue/httpie
```

## Validation Commands

### Go Binary Validation
```bash
# Verify binary builds
go build -o sequoia

# Check for runtime errors
./sequoia -help

# Run simple test to verify framework works
./sequoia
```

### Docker Container Validation
```bash
# Verify container builds
docker images | grep sequoiatools
docker images | grep couchbase-watson

# Test container starts successfully
docker run --rm sequoiatools/testrunner help
```

### Test Execution Validation
```bash
# Run default test
./sequoia

# Run simple KV test
./sequoia -scope tests/simple/scope_small.yml -test tests/simple/test_simple.yml

# Check test results
cat logs/results.tap4j

# Verify cleanup (check no orphaned containers)
docker ps -a | grep sequoia
docker rm -f $(docker ps -a -q)  # Clean up if needed
```

## Component-Specific Testing

### Core Framework (lib/)
- No Go unit tests found in repo
- Manual testing via end-to-end test execution
- Verify by running: `./sequoia`

### Testrunner (Python)
- Tests executed through Docker container
- Validation: `./sequoia -scope tests/testrunner/scope_simple.yml -test tests/testrunner/test_buildSanity.yml`
- Log location: `logs/` directory

### Service-Specific Tests

**Analytics:**
```bash
./sequoia -scope tests/analytics/scope_analytics.yml -test tests/analytics/test_analytics.yml
```

**Eventing:**
```bash
./sequoia -scope tests/eventing/scope_eventing.yml -test tests/eventing/test_eventing.yml
```

**FTS (Full Text Search):**
```bash
./sequoia -scope tests/simple/scope_fts.yml -test tests/simple/test_fts.yml
```

**N1QL (Query):**
```bash
./sequoia -scope tests/simple/scope_n1ql.yml -test tests/simple/test_query.yml
```

**Views:**
```bash
./sequoia -scope tests/simple/scope_views.yml -test tests/simple/test_views.yml
```

**XDCR (Cross Data Center Replication):**
```bash
./sequoia -scope tests/xdcr/scope_4x4x4Node.yml -test tests/xdcr/test_xdcrVol.yml
```

**Secondary Index (2i):**
```bash
./sequoia -scope tests/2i/scope_idx_rebalance_replica.yml -test tests/2i/test_idx_rebalance_replica.yml
```

**Integration:**
```bash
./sequoia -scope tests/integration/scope_Xattrs_Vulcan.yml -test tests/integration/test_allFeatures.yml
```

## Debugging and Diagnostics

### Debugging
```bash
# Enable debug logs (check logs/debug)
# Go pprof endpoint runs on :30000 by default
curl http://localhost:30000/debug/pprof/
```

### Container Inspection
```bash
# Check running containers
docker ps

# Inspect container logs
docker logs <container_id>

# Connect to container shell
docker exec -it <container_id> /bin/bash
```

### Log Locations
- `logs/results.tap4j` - Test results in TAP format
- `logs/debug` - Debug logs (if enabled)
- Container logs accessible via `docker logs <container_id>`

## Pre-Commit Checklist

Not applicable (no git hooks or pre-commit configuration found). For code changes:

- [ ] `go build -o sequoia` succeeds without errors
- [ ] Relevant Docker containers build successfully
- [ ] At least one simple test runs successfully (`./sequoia`)
- [ ] No sensitive data in generated files (`logs/`, `hosts.json`)
- [ ] Config changes validated against schema (YAML syntax)

## Known Validation Gaps

- **No Go unit tests**: No automated test coverage for Go framework code
- **No linting**: No automated code quality checks (golangci-lint, gofmt)
- **No type errors**: No explicit type checking commands
- **No smoke tests**: No quick validation test suite
- **No CI/CD**: No automated build/test pipeline
- **No coverage reports**: No code coverage metrics

## Manual Validation Steps

1. **Framework Build:**
   ```bash
   go mod tidy
   go build -o sequoia
   ```

2. **Container Builds:**
   ```bash
   ./build.sh  # or build specific containers
   docker images | grep -E "sequoiatools|couchbase"
   ```

3. **Simple Test Run:**
   ```bash
   ./sequoia
   # Check exit code (should be 0 on success)
   # Check logs/results.tap4j for results
   ```

4. **Cleanup Verification:**
   ```bash
   docker ps -a
   # Ensure no orphaned sequoia containers remain
   ```

5. **Configuration Validation:**
   ```bash
   # Check config.yml syntax
   python -c "import yaml; yaml.safe_load(open('config.yml'))"
   ```

## Integration Test Suites

**Version-Specific Tests:**
- 7.2: `tests/integration/7.2/test_7.2.yml`, `tests/integration/7.2/scope_7.2_magma.yml`
- 7.6: `tests/integration/7.6/test_7.6.yml`, `tests/2i/7.6/`
- 7.7: `tests/integration/7.7/test_7.7.yml`
- 8.0: `tests/integration/8.0/test_8.0.yml`
- 8.1: `tests/integration/8.1/test_8.1.yml`

**Release-Specific Tests:**
- Alice: `tests/*/alice/*`
- Cheshire Cat: `tests/*/cheshire-cat/*`
- Neo: `tests/*/neo/*`
- Mad Hatter: `tests/*/mad-hatter/*`
- Vulcan: Integration tests with `_vulcan` in names
- Morpheus: 2i tests with `morpheus` prefix
- Elixir: 2i tests with `elixir` prefix

## Performance Testing

**TPCC:**
```bash
./sequoia -scope tests/2i/scope_2i_tpcc.yml -test tests/2i/test_2i_tpcc.yml
```

**YCSB:**
```bash
./sequoia -scope tests/ycsb/scope_ycsb_workload.yml -test tests/ycsb/test_ycsb_workload.yml
```

**Vegeta:**
```bash
./sequoia -scope tests/simple/scope_medium.yml -test tests/simple/test_vegetaDemo.yml
```

**Pillowfight (KV workload):**
```bash
# Used in many test templates
./sequoia -scope tests/simple/scope_medium.yml -test tests/simple/test_simple.yml
```

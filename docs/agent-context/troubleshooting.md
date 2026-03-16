# Troubleshooting - Sequoia

## Common Setup Issues

### Docker Daemon Connection Issues

**Symptom:** `Cannot connect to Docker daemon` or connection refused

**Causes:**
- Docker service not running
- Incorrect client endpoint in config.yml
- TLS certificate issues for HTTPS endpoints

**Solutions:**
```bash
# Check Docker is running
docker ps

# start dockerd
nohup dockerd -H unix:///var/run/docker.sock -H tcp://127.0.0.1:2375 --data-root=/data &

# Test alternative endpoints
# For local docker socket:
client: "unix:///var/run/docker.sock"

# For Docker Machine (older macOS/Windows):
client: "https://192.168.99.100:2376"

# For remote Docker with HTTP (insecure):
client: "http://172.23.97.124:2375"

# For remote Docker with HTTPS:
client: "https://<host>:2376"
# Ensure cert files are in .docker directory
```

### Go Build Failures

**Symptom:** Build errors or missing dependencies

**Causes:**
- Go version mismatch (requires 1.21.6+)
- Missing dependencies after go.mod changes
- Network issues downloading modules

**Solutions:**
```bash
# Check Go version
go version

# Update dependencies
go mod tidy
go mod verify

# Clean build
go clean
go build -o sequoia
```

### Container Build Failures

**Symptom:** Docker build fails for containers

**Causes:**
- Network issues downloading base images
- Build arguments missing
- Invalid Dockerfile syntax
- Submodule not checked out (testrunner)

**Solutions:**
```bash
# Pull base images first
docker pull ubuntu
docker pull centos:7

# Check submodules
cd containers/testrunner/src
git status

# Rebuild with verbose output
docker build --no-cache --progress=plain -t sequoiatools/testrunner containers/testrunner

# Build with specific build number
./build.sh 1818
```

## Test Execution Problems

### Test Hangs or Times Out

**Symptom:** Test runs but never completes or times out

**Causes:**
- Container not starting properly
- Service not becoming available
- Network connectivity issues between containers
- Wait condition never satisfied

**Solutions:**
```bash
# Check running containers
docker ps

# Check container logs for startup issues
docker logs <container_id>

# Check container health
docker inspect <container_id> | grep -A 10 "Health"

# Verify network connectivity
docker network inspect <network_name>
docker exec <container_id> ping <other_container>

# Increase timeout or remove wait conditions from test YAML
```

### Container Cleanup Issues

**Symptom:** Orphaned containers or resources remain after test

**Causes:**
- Test crashed before cleanup
- `skip_teardown: true` in config
- Manual intervention during test
- Provider not properly removing containers

**Solutions:**
```bash
# Clean up all sequoia containers
docker rm -f $(docker ps -a -q | xargs -I {} docker inspect {} --format '{{.Name}}' | grep sequoia | tr -d '/')

# Force stop all containers (caution!)
docker rm -f $(docker ps -a -q)

# Remove custom networks
docker network prune

# Remove volumes
docker volume prune

# Check logs for cleanup errors
cat logs/results.tap4j
```

### Provider Selection Issues

**Symptom:** `provider not found` or infrastructure not provisioned

**Causes:**
- Invalid provider name in config.yml
- Provider-specific requirements not met
- File provider server unreachable

**Solutions:**
```bash
# Verify provider setting in config.yml
provider: docker  # valid: docker, file, dev, swarm

# For file provider, check hosts.json exists
cat hosts.json

# For swarm provider, ensure swarm is initialized
docker swarm init

# Verify provider options file exists
ls providers/docker/options.yml
```

## Service-Specific Issues

### FTS (Full Text Search) Failures

**Symptom:** FTS indexing or search tests fail

**Causes:**
- FTS service not enabled in scope
- Index definitions not created
- Vector search schema errors (for Neo+)

**Solutions:**
```bash
# Check FTS service is in scope
grep -A 5 "services:" tests/*/scope_fts.yml

# Check FTS container logs
docker logs $(docker ps | grep ftsindexmanager | awk '{print $1}')

# Verify vector loader for Neo tests
docker logs $(docker ps | grep vectorloader | awk '{print $1}')

# Check service health
curl http://<host>:8094/api/indexStatus
```

### Eventing Service Failures

**Symptom:** Eventing functions not executing or processing

**Causes:**
- Eventing service not provisioned
- Function deployment errors
- DCP connection issues

**Solutions:**
```bash
# Check eventing service is provisioned
docker ps | grep eventing

# Check function deployment logs
docker logs $(docker ps | grep eventing | awk '{print $1}')

# Verify DCP stream connections
curl http://<host>:8091/pools/default/buckets/<bucket>/stats
```

### N1QL Query Failures

**Symptom:** Query tests fail with errors

**Causes:**
- Query service not enabled
- Indexes not created before queries
- Query syntax errors

**Solutions:**
```bash
# Check query service is available
docker ps | grep query_manager

# Test query service endpoint
curl http://<host>:8093/query/service

# Verify indexes exist
curl http://<host>:8093/query/service -d 'SELECT * FROM system:indexes'

# Check query manager logs
docker logs $(docker ps | grep query_manager | awk '{print $1}')
```

### Analytics Service Failures

**Symptom:** Analytics queries fail or service not responding

**Causes:**
- Analytics service not provisioned
- CBAS datasets not created
- Schema inference issues

**Solutions:**
```bash
# Check analytics service
docker ps | grep analytics

# Check analytics manager logs
docker logs $(docker ps | grep analyticsmanager | awk '{print $1}')

# Verify CBAS datasets
curl http://<host>:8095/analytics/service -d 'SELECT * FROM Metadata.`Dataset`'
```

## Performance and Resource Issues

### Out of Memory

**Symptom:** Container killed due to OOM or system sluggish

**Causes:**
- Too many containers or large cluster
- Insufficient system resources
- Memory leak in test

**Solutions:**
```bash
# Check system memory
free -h  # Linux
vm_stat  # macOS

# Monitor container memory usage
docker stats

# Reduce cluster size or scale
# Edit scope file to reduce node count or bucket RAM

# Increase Docker memory limit (Docker Desktop settings)
```

### Disk Space Issues

**Symptom:** Docker fails due to insufficient disk space

**Causes:**
- Too many container images
- Large test data not cleaned up
- Log accumulation

**Solutions:**
```bash
# Check disk space
du -sh

# Clean up Docker
docker system prune -a

# Remove old test logs
rm -rf logs/*.tap4j
rm -rf logs/debug/*

# Clean specific volumes
docker volume prune
```

### Slow Test Execution

**Symptom:** Tests take longer than expected

**Causes:**
- Network delay between containers
- Slow container startup
- Inefficient workloads

**Solutions:**
```bash
# Check container startup times
docker ps --format "table {{.Names}}\t{{.Status}}"

# Use --network for better container communication
./sequoia --network cbl

# Optimize Docker daemon (adjust resources in Docker Desktop)

# Reduce scaling factor in config.yml
# scale: 0.5  # for half-sized workloads
```

## Log and Debugging

### Accessing Logs

**Sequoia logs:** `logs/results.tap4j` (test results), `logs/debug/*` (debug output)

**Container logs:**
```bash
# Specific container
docker logs <container_id>

# All sequoia containers
for id in $(docker ps -a | grep sequoia | awk '{print $1}'); do
  echo "=== Container $id ==="
  docker logs $id | tail -n 50
done
```

### Debug Mode

Sequoia includes a debug HTTP server on port 30000:

```bash
# Access pprof profiles
curl http://localhost:30000/debug/pprof/

# Get goroutine dump
curl http://localhost:30000/debug/pprof/goroutine?debug=2

# Get heap profile
go tool pprof http://localhost:30000/debug/pprof/heap
```

### TAP4J Result Validation

```bash
# Parse TAP4J results
# Use a TAP parser or examine manually
cat logs/results.tap4j | grep -E "<duration|<status|<name"

# Check for failures
grep -i "fail" logs/results.tap4j
grep -i "error" logs/results.tap4j
```

## Network Issues

### Container Communication Problems

**Symptom:** Containers cannot reach each other

**Causes:**
- Wrong network mode
- DNS resolution issues
- Port conflicts

**Solutions:**
```bash
# Check network configuration
docker network inspect bridge

# Use custom network
docker network create cbl
./sequoia --network cbl

# Check DNS resolution
docker exec <container> nslookup <other_container_name>

# Check port bindings
docker port <container_id>
```

### Firewall/VPN Issues

**Symptom:** Cannot connect to remote Docker daemon or servers

**Causes:**
- Firewall blocking ports
- VPN connection unstable
- Corporate network policies

**Solutions:**
```bash
# Check connectivity to Docker endpoint
ping <docker_host>
telnet <docker_host> 2375  # or 2376 for HTTPS

# Check VPN status (if applicable)
# Verify routing

# Test with alternative endpoint in config.yml
```

## YAML Configuration Problems

### Invalid YAML Syntax

**Symptom:** Parser errors or silently incorrect config

**Causes:**
- Bad indentation
- Unquoted special characters
- Invalid YAML structure

**Solutions:**
```bash
# Validate YAML syntax
python3 -c "import yaml; yaml.safe_load(open('config.yml'))"
python3 -c "import yaml; yaml.safe_load(open('tests/simple/scope_small.yml'))"

# Use YAML linter
yamllint config.yml tests/**/*.yml  # if yamllint is installed
```

### Template Resolution Issues

**Symptom:** Variables or templates not resolving

**Causes:**
- Missing template file
- Incorrect variable syntax
- Scope not providing required variables

**Solutions:**
```bash
# Check template exists
ls tests/templates/kv.yml

# Verify variable syntax in tests
# Template: {{.Orchestrator}}, {{.Bucket}}, {{.Scale 2000}}

# Check scope provides required variables
grep -A 10 "servers:" tests/simple/scope_small.yml
```

## Escalation Points

When to escalate to higher-level support:

1. **Reproduceable bugs** in Sequoia framework (Go code)
   - Document exact steps to reproduce
   - Include logs from `logs/` directory
   - Provide config.yml and test YAML files

2. **Container build failures** that persist across retries
   - Network/firewall issues
   - Base image availability
   - Docker daemon version compatibility

3. **Test logic issues** (test files not validating correctly)
   - Review test specification in YAML files
   - Check service provisioning in scope files
   - Verify expected results match test assertions

4. **Performance regressions** in test execution time
   - May indicate Docker or infrastructure issues
   - May require cluster size adjustments

## Recovery Procedures

### Full Environment Reset

```bash
# Stop all containers
docker rm -f $(docker ps -a -q)

# Clean networks
docker network prune -f

# Clean volumes
docker volume prune -f

# Build containers
./build.sh

# Run simple test to verify
./sequoia
```

### Partial Reset (Keep Images)

```bash
# Remove containers only
docker rm -f $(docker ps -a -q)

# Clean logs
rm -rf logs/*

# Rebuild framework binary
go build -o sequoia

# Run test
./sequoia
```

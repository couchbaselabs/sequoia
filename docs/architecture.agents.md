# Architecture - SequoiaTesting Framework

## System Overview

Sequoia is a Docker-based testing framework that orchestrates Couchbase infrastructure provisioning and test execution. The framework follows a declarative model:
- **Scopes** define required infrastructure (servers, buckets, users, services)
- **Tests** define actions to execute against the infrastructure
- **Providers** abstract infrastructure provisioning mechanisms
- **Containers** encapsulate test execution frameworks and workloads

## Core Components

### 1. Entry Point (run.go)
```
/run.go
  -> lib/flags.go (parse CLI arguments)
  -> lib/container.go (create ContainerManager)
  -> lib/scope.go (provision infrastructure)
  -> lib/test.go (execute test actions)
```

**Key responsibilities:**
- Parse command-line flags
- Initialize ContainerManager with Docker client
- Create Scope for infrastructure provisioning
- Create Test for action execution
- Launch debug HTTP server on port 30000

### 2. Container Manager (lib/container.go)
```
ContainerManager
  - Docker client (fsouza/go-dockerclient)
  - Provider type: docker, swarm, file, dev
  - Network configuration
  - Active container tracking
```

**Functions:**
- Container lifecycle: create, start, stop, remove
- Volume management for test data
- Network management for inter-container communication
- Container health checks and wait conditions

### 3. Provider Framework (lib/provider.go)

**Provider Interface:**
```go
type Provider interface {
    ProvideCouchbaseServers(filename *string, servers []ServerSpec)
    ProvideSyncGateways(syncGateways []SyncGatewaySpec)
    ProvideAccels(accels []AccelSpec)
    ProvideLoadBalancer(loadBalancer LoadBalancerSpec)
    GetHostAddress(name string) string
    GetType() string
    GetRestUrl(name string) string
}
```

**Provider Implementations:**
- **DockerProvider** - Spins up Couchbase containers dynamically
  - Uses Docker API to create/destroy containers
  - Maps container ports to host ports
  - Creates Docker networks for cluster communication
  - Supports base template images (ubuntu-gcc, ubuntu-python, ubuntu-vbr)

- **FileProvider** - Connects to pre-existing remote servers
  - Reads server definitions from hosts.json
  - Connects via SSH/REST API
  - No container lifecycle management
  - Useful for testing against production-like infrastructure

- **SwarmProvider** - Extends DockerProvider for Docker Swarm
  - Uses Swarm services instead of containers
  - Supports distributed test execution
  - Better for large-scale testing

- **ClusterRunProvider/DevProvider** - Local development mode
  - Uses local Couchbase cluster installation
  - No Docker overhead
  - Faster iteration for local development

### 4. Scope Management (lib/scope.sgo)

**Scope Processing Pipeline:**
```
YAML scope file -> Parse -> Validate -> Provision -> Configure
```

**Scope Components:**
- **Servers**: Couchbase server nodes (count, RAM, services)
- **Buckets**: Data buckets (RAM quota, replicas, eviction policy)
- **Users**: RBAC users, roles, authentication
- **Sync Gateways**: Mobile sync endpoints
- **Server Groups**: Rack awareness configuration
- **Services per node**: Data, Index, Query, Search, Analytics, Eventing

**Provisioning Steps:**
1. Reserve ports for each service per node
2. Create Docker containers for Couchbase servers
3. Wait for Couchbase REST API to be available
4. Configure buckets via REST API
5. Create users via REST API
6. Configure services (FTS, Eventing, etc.)
7. Optional: Create server groups and configure rebalance

### 5. Test Execution (lib/test.go)

**Test Processing Pipeline:**
```
YAML test file -> Parse -> Resolve Templates -> Execute Actions -> Collect Results
```

**Action Types:**
- **Container actions**: Start test workload containers (pillowfight, ycsb, perfrunner, etc.)
- **Template actions**: Include reusable test sections
- **Section actions**: Iterate over subsets of data
- **CLI commands**: Execute shell commands in containers
- **REST API calls**: Configure services via Couchbase REST API

**Execution Model:**
- Actions executed sequentially by default
- Support for concurrency with `concurrency` parameter
- Wait conditions block until criteria met
- Repeat loops for multiple iterations
- Conditional execution with `until` parameter

**Template System:**
```
tests/templates/kv.yml -> Common KV operations
tests/templates/n1ql.yml -> Query operations
tests/templates/fts.yml -> Full-text search operations
tests/templates/bucket.yml -> Bucket configuration
```

**Variable Substitution:**
- `{{.Orchestrator}}` - Couchbase orchestrator node
- `{{.Bucket}}` - Bucket name
- `{{.Scale N}}` - Scaled value (N * scale factor)
- `{{.AuthPassword}}` - Authentication password
- `{{.Nodes}}` - Comma-separated list of all cluster nodes 
- `{{.RestUsername}}` -  REST API username 
- `{{.RestPassword}}` -  REST API password 
- `{{.InActiveNode}}` -  Returns first inactive node 
- `{{.ActiveDataNode N}}` -  Returns Nth active data node in the cluster  


### 6. REST API Client (lib/rest.go)

**Couchbase API Operations:**
```
Cluster operations: Get nodes, Rebalance, Failover
Bucket operations: Create, Delete, Flush, Modify
User operations: RBAC user management
Service operations: Query, Search, Analytics, Eventing
```

**REST Endpoints:**
- `/pools` - Cluster information
- `/pools/default/buckets` - Bucket management
- `/settings/rbac/users` - User management
- `/query/service` - Query service
- `/api/indexStatus` - FTS status

### 7. Specification Structures (lib/spec.go)

**Data Models:**
```yaml
ServerSpec:
  name, count, ram, services
  rest_username, rest_password, rest_port
  init_nodes, buckets, users

BucketSpec:
  name, ram, replica, type
  eviction, ddocs, storage
  durability, compression
  collections, scopes (for Couchbase 7.x)

UserSpec:
  name, password, roles
  auth_domain (local, external)

ActionSpec:
  image, command, volumes, wait
  template, args, section
  describe, requires, alias
```

## Container-Based Workloads

### Test Framework Containers

**Testrunner (Python):**
- Location: `containers/testrunner/` (submodule)
- Base: CentOS 7 with Python 3.7.6
- Dependencies: libcouchbase, testrunner repo
- Entry point: `./testrunner` script
- Usage: Python-based test execution (via testrunner submodule)

**Perfrunner (Python):**
- Location: `containers/perfrunner/`
- Base: CentOS 6 with Python 2.7
- Dependencies: libcouchbase, perfrunner repo
- Entry point: Python perfrunner module
- Usage: Performance benchmarking

### Service-Specific Workload Containers

**Pillowfight:**
- KV workload generator
- Uses libcouchbase SDK
- Configurable: document size, operation count, batch size

**Gideon:**
- Document mutation tool
- Creates and updates documents
- Supports various mutation patterns

**Catapult:**
- High-throughput document loader
- Used for scale testing

**YCSB:**
- Yahoo! Cloud Serving Benchmark
- Multiple workloads: read-heavy, write-heavy, scan, mixed
- Used for NoSQL performance comparison

**Vegeta:**
- HTTP load testing
- Used for API endpoint testing

**TPCC:**
- TPC-C OLTP benchmark
- Tests transaction processing performance

**MagmaLoader:**
- High ops rate

### Service Management Containers

**Query Manager:**
- Manages N1QL query service
- Creates/deletes indexes
- Executes queries

**FTS Index Manager:**
- Manages full-text search indexes
- Vector search loaders (Go and Python implementations)
- Synonym loaders for search testing

**Eventing Containers:**
- Deploy and run JavaScript eventing functions
- Monitor function execution
- Test DCP integration

**GSI Containers:** 
- Manage global secondary indexes

**Analytics Containers:**
- Manage Analytics Service (CBAS)
- Create datasets and indexes
- Execute analytics queries

## Workflow Examples

### Simple KV Test

```
1. Parse config.yml:
   - client: unix:///var/run/docker.sock
   - provider: docker
   - scope: tests/simple/scope_small.yml
   - test: tests/simple/test_simple.yml

2. Provision scope (tests/simple/scope_small.yml):
   - Start 1 Couchbase container
   - Configure default bucket (75% RAM, 1 replica)
   - Create admin user

3. Create test runner (tests/simple/test_simple.yml):
   - Include template: tests/templates/kv.yml
   - Start pillowfight container
   - Run KV operations
   - Wait for completion

4. Collect results:
   - Generate TAP4J output in logs/results.tap4j

5. Cleanup:
   - Stop and remove all containers
   - Remove Docker networks
```

### Multi-Service Integration Test

```
1. Parse scope with multiple services:
   - 3 Couchbase servers
   - Services: data, index, query, search, analytics, eventing

2. Provision infrastructure:
   - Create 3 server containers
   - Wait for all services to start
   - Configure 3 buckets with different types
   - Set up RBAC users with various roles
   - Create indexes for query service
   - Configure FTS indexes
   - Deploy eventing functions

3. Execute test actions:
   - Load data via pillowfight
   - Run N1QL queries
   - Execute FTS searches
   - Run analytics queries
   - Trigger eventing functions
   - Perform rebalance operation
   - Perform failover test

4. Validate results:
   - Check data consistency
   - Verify query results
   - Validate FTS search results
   - Check analytics query outputs
   - Verify eventing function execution
   - Confirm rebalance completed
   - Verify failover worked

5. Cleanup:
   - Remove all infrastructure
   - Clean up volumes and networks
```

## Network Architecture

### Container Networking

**Default Bridge Network:**
- Containers communicate via bridge network
- DNS resolution by container name
- Port mapping for external access

**Custom Docker Networks:**
- Created with `--network` flag
- Better isolation and performance
- Supports service discovery

**Port Assignments:**
- 8091: Couchbase REST API
- 11210: Couchbase data service
- 8093: Query service
- 8094: FTS service
- 8095: Analytics service
- 8096: Eventing service

### Host Serialization

**Host to IP Mapping:**
- Container names resolved to internal IPs
- HostSerializer converts names for container communication
- Generated in `hosts.json` during setup

## Data Flow

### Test Provisioning Flow
```
config.yml
  -> Parse flags
    -> Select provider
      -> Read scope YAML
        -> Create Provider
          -> Call ProvideCouchbaseServers()
            -> Create Docker containers
              -> Configure services via REST
                -> Store in Scope object
```

### Test Execution Flow
```
Test YAML
  -> Parse actions
    -> Resolve templates
      -> For each action:
        - Parse ActionSpec
        - Expand variables ({{}} syntax)
        - If template: expand and recurse
        - If container: start container
        - If wait: poll until condition met
        - If command: execute in container
        - Collect results
          -> Generate TAP4J
```

## Configuration Boundaries

### Scope File Responsibility
- Infrastructure definitions only
- No test logic or assertions
- Service enabling/disabling
- Resource allocation (RAM, CPU)

### Test File Responsibility
- Test actions and sequences
- Workload definitions
- Assertions and validations
- Template composition

### Provider Strategy
- Abstraction of infrastructure mechanism
- Pluggable implementations
- Provider-specific options (e.g., Docker CPU/memory limits)

## Error Handling

### Container Startup Failures
- Retry logic with exponential backoff
- Health check polling
- Timeout escalation to failure

### Service Configuration Failures
- REST API error detection
- Graceful degradation if optional services fail
- Detailed error logging in `logs/debug`

### Test Execution Failures
- Continue to next action by default (unless `wait: true`)
- Capture failure in TAP4J results
- Preserve logs for debugging

## Extension Points

### Custom Providers
- Implement `Provider` interface
- Register in `NewProvider()` switch statement
- Add provider-specific options to YAML

### Custom Workload Containers
- Create Dockerfile in `containers/`
- Update `build.sh` to build container
- Reference in test YAML via `image:` field

### Custom Templates
- Create YAML file in `tests/templates/`
- Reference in tests via `template:` field
- Use variable substitution for flexibility

## Validation Clues

### Successful Test Indicators
- Exit code 0 from sequoia binary
- `logs/results.tap4j` contains `<passCount>` > 0
- No ERROR or FAIL entries in logs
- All containers cleaned up (`docker ps -a` shows no sequoia containers)

### Infrastructure Health Checks
- REST API accessible: `curl http://<host>:8091/pools`
- All services started: Check node services in REST API
- Buckets created: Check `/pools/default/buckets`
- Indexes ready: Check query service index status

### Container Status Validation
```bash
# Check container is running
docker ps | grep <container_name>

# Check health status
docker inspect <container_id> --format='{{.State.Health.Status}}'

# Check container logs for errors
docker logs <container_id> | grep -i error
```

## Performance Characteristics

### Startup Latency
- Container creation: 2-5 seconds per container
- Couchbase initialization: 10-30 seconds
- Service startup: 5-10 seconds per service
- Total cluster startup: 30-120 seconds (depends on cluster size)

### Test Execution Time
- Simple KV test: 1-5 minutes
- Multi-service integration: 10-30 minutes
- Large-scale tests (1000+ collections): 1-2 hours
- Longevity tests: 4-24 hours

### Resource Requirements
- Memory: 4-8 GB minimum for small tests, 16-32 GB for integration tests
- CPU: 4 cores recommended for parallel container operations
- Disk: 20 GB for images, 50+ GB for test data (if not cleaned up frequently)

### Scalability Limits
- Max nodes: Limited by Docker daemon resources
- Max containers: Limited by system (typically 100-200)
- Max buckets: 1000+ supported (tested in integration suite)
- Max collections per bucket: 1000+ supported (tested in 2i tests)

## Security Considerations

### Docker Daemon Access
- Unix socket: No authentication (localhost only)
- HTTP port 2375: No authentication (not recommended)
- HTTPS port 2376: Requires TLS certificates

### Credentials in Tests
- Test files often contain default credentials
- Avoid committing production credentials
- Use environment variables for sensitive data

### Network Isolation
- Containers on custom network isolated from external
- Port mappings expose services to host
- Use firewall rules for remote Docker daemon access

## Monitoring and Debugging

### Built-in Debugging
- Go pprof endpoint on port 30000
- Container logs accessible via `docker logs`
- Sequoia logs in `logs/results.tap4j` and `logs/debug`

### Health Monitoring
- Container health checks
- Service availability via REST API
- Test action timeouts
- See eagle-eye - https://github.com/couchbaselabs/eagle-eye

### Performance Profiling
- Go runtime profiling via pprof
- Container resource usage via `docker stats`
- Network performance via container ping/traceroute

# Sequoia — Design Document

> **Version:** 1.0  
> **Last Updated:** March 2026  
> **Audience:** Engineers, contributors, and anyone wanting to understand how Sequoia works

---

## Table of Contents

1. [What is Sequoia?](#1-what-is-sequoia)
2. [Core Design Principles](#2-core-design-principles)
3. [High-Level Architecture](#3-high-level-architecture)
4. [Key Concepts](#4-key-concepts)
5. [Component Design](#5-component-design)
6. [Scope File Design](#6-scope-file-design)
7. [Test File Design](#7-test-file-design)
8. [Provider Abstraction](#8-provider-abstraction)
9. [Container Workloads](#9-container-workloads)
10. [Data Flow](#10-data-flow)
11. [Networking](#11-networking)
12. [Error Handling Strategy](#12-error-handling-strategy)
13. [Extension Points](#13-extension-points)
14. [Design Decisions and Trade-offs](#14-design-decisions-and-trade-offs)

---

## 1. What is Sequoia?

Sequoia is a **scalable, Docker-based testing framework** designed specifically for testing Couchbase clusters. Its primary goal is to make it easy to spin up realistic Couchbase environments and run a wide variety of workloads against them — all from a single command.

Instead of manually configuring servers, creating buckets, and running test scripts, you describe what you want in YAML files. Sequoia reads those files and does the heavy lifting.

**What Sequoia does:**

- Provisions Couchbase server clusters (via Docker or real machines)
- Creates buckets, users, indexes, and service configurations
- Runs test workloads inside containers (KV load, N1QL queries, FTS, Analytics, etc.)
- Collects and reports results in TAP4J format
- Cleans up everything when done

**What Sequoia does NOT do:**

- Replace unit tests or integration tests within Couchbase Server itself
- Manage application-level deployments
- Serve as a general-purpose CI/CD pipeline
- Built-in verification of essential features

---

## 2. Core Design Principles

### 2.1 Declarative Infrastructure

You describe *what* you need, not *how* to build it. A scope YAML file declares the desired state of the cluster — how many nodes, which services, which buckets, which users — and Sequoia figures out how to provision it.

### 2.2 Separation of Concerns

| Concern | Where it lives |
|---|---|
| Infrastructure definition | `scope_*.yml` files |
| Test actions and workloads | `test_*.yml` files |
| Reusable test patterns | `tests/templates/*.yml` |
| Workload execution logic | Containers in `containers/` |
| Provisioning mechanism | Provider implementations in `lib/` |

This separation means you can reuse the same scope with different tests, or swap out the provider (Docker vs. real hardware) without changing the test.

### 2.3 Container-First Workloads

Every test workload runs inside a Docker container. This ensures:
- **Reproducibility** — same container image, same results
- **Isolation** — workloads don't interfere with each other
- **Portability** — works on any machine with Docker
- **Fault tolerance** — ensures continuity during node outages

### 2.4 Provider Abstraction

The infrastructure provider is a pluggable component. The same scope and test can be run against:
- Locally-created Docker containers (development and CI)
- Pre-existing remote servers (performance labs, cloud VMs)
- Docker Swarm clusters (large-scale tests)

---

## 3. High-Level Architecture

```
┌─────────────────────────────────────────────────────┐
│                    sequoia (run.go)                  │
│                                                     │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────┐ │
│  │ flags.go │  │ scope.go │  │     test.go        │ │
│  │ (CLI)    │  │ (Infra)  │  │ (Test Execution)   │ │
│  └──────────┘  └──────────┘  └────────────────────┘ │
│                      │                │              │
│               ┌──────────────────┐    │              │
│               │   provider.go    │    │              │
│               │ (Docker/File/..) │    │              │
│               └──────────────────┘    │              │
│                                       │              │
│                         ┌─────────────────────────┐  │
│                         │     container.go        │  │
│                         │  (Docker Container Mgr) │  │
│                         └─────────────────────────┘  │
└─────────────────────────────────────────────────────┘
          │                           │
          ▼                           ▼
 Couchbase Cluster             Test Containers
 (Servers / Buckets)    (pillowfight, ycsb, testrunner…)
```

At a high level, Sequoia:
1. Reads configuration from `config.yml`
2. Provisions infrastructure using the chosen provider
3. Executes test actions (which launch containers or call REST APIs)
4. Collects results and cleans up

---

## 4. Key Concepts

### Scope

A **scope** is a YAML file that fully describes the infrastructure required for a test. It includes:
- Couchbase server cluster definitions (node count, RAM, services)
- Bucket definitions (name, storage engine, eviction policy, etc.)
- User definitions (RBAC roles)
- Optional: Sync Gateway instances, server groups

A scope represents the *environment* — not the tests themselves.

### Test

A **test** is a YAML file that defines a sequence of **actions** to run against a provisioned scope. Actions can:
- Start container workloads (e.g., pillowfight, YCSB)
- Execute REST API calls against Couchbase
- Wait for specific conditions
- Include reusable templates

### Template

A **template** is a reusable YAML snippet included in tests. For example, a template might define the standard steps to create indexes before running queries. Templates live in `tests/templates/`.

### Provider

A **provider** is the mechanism used to provision Couchbase servers. Providers are swapped via `config.yml`, so tests are infrastructure-agnostic.

### Container

A **container** is a Docker image that contains a workload — a tool, benchmark, or test framework — that runs against the provisioned Couchbase cluster.

---

## 5. Component Design

### 5.1 Entry Point (`run.go`)

The main entry point that ties everything together:

1. Parses CLI flags (`lib/flags.go`)
2. Creates a `ContainerManager` with the Docker client
3. Provisions the scope (infrastructure) via `lib/scope.go`
4. Runs the test actions via `lib/test.go`
5. Exposes a debug HTTP server on port **30000** (Go pprof)

### 5.2 Container Manager (`lib/container.go`)

Manages the full lifecycle of Docker containers:
- **Create** containers from images
- **Start** containers and attach volumes/networks
- **Stop and remove** containers on cleanup
- **Health checks** — poll containers until they are ready
- **Volume management** — mount test data directories
- **Network management** — create Docker networks for cluster communication

### 5.3 Scope Manager (`lib/scope.go`)

Reads a scope YAML and provisions the described infrastructure:

```
Parse YAML
  → Validate fields
  → Select provider
  → Provision servers (containers or remote hosts)
  → Wait for Couchbase REST API
  → Create buckets via REST API
  → Create users via REST API
  → Configure services (FTS, Eventing, Analytics…)
  → Optionally set up server groups and rebalance
```

### 5.4 Test Runner (`lib/test.go`)

Reads a test YAML and executes actions:

```
Parse YAML
  → Resolve template includes
  → For each action:
      - Expand variables ({{ .Orchestrator }}, {{ .Bucket }}, etc.)
      - If container action: start the workload container
      - If REST action: call Couchbase REST API
      - If wait action: poll until condition is met
      - If repeat/loop: iterate with counter
  → Collect pass/fail results
  → Write TAP4J results file
```

**Concurrency** is supported — actions can run in parallel by setting the `concurrency` parameter.

### 5.5 Provider (`lib/provider.go`)

Implements the `Provider` interface:

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

| Provider | Description |
|---|---|
| `docker` | Spins up Couchbase containers using the Docker API |
| `file` | Connects to pre-existing remote servers via `hosts.json` |
| `swarm` | Extends the Docker provider for Docker Swarm clusters |
| `dev` | Uses a local Couchbase cluster-run installation (no Docker overhead) |

### 5.6 REST Client (`lib/rest.go`)

A thin wrapper around the Couchbase REST API, used for provisioning:
- Cluster initialization and rebalance
- Bucket creation, deletion, flush
- RBAC user management
- Service configuration (N1QL, FTS, Analytics, Eventing)

### 5.7 Spec Structures (`lib/spec.go`)

Go structs that map directly to YAML keys:

| Struct | Purpose |
|---|---|
| `ServerSpec` | Describes a Couchbase cluster (node count, RAM, services) |
| `BucketSpec` | Describes a bucket (name, RAM %, storage engine, eviction, etc.) |
| `UserSpec` | Describes an RBAC user (name, password, roles) |
| `ActionSpec` | Describes a test action (image, command, wait conditions) |

---

## 6. Scope File Design

A scope file declares all infrastructure needed for a test run. Here is an annotated breakdown of the key sections:

### Servers

```yaml
servers:
  - name: local          # cluster name used in tests
    count: 5             # number of Couchbase nodes
    ram: 50%             # percentage of host RAM to allocate
    index_ram: 80%       # RAM for Index service
    services:
      index: 2           # 2 nodes run the Index service
      query: 1           # 1 node runs the Query service
      fts: 1             # 1 node runs the FTS service
    init_nodes: 5        # number of nodes to initialize in the cluster
    buckets: default,b2  # comma-separated list of buckets to create
    users: default       # comma-separated list of users to create
```

- Multiple server entries create **multiple clusters** (e.g., for XDCR testing).
- `count` and `init_nodes` can differ to leave spare nodes available for rebalance-in tests.

### Buckets

```yaml
buckets:
  - name: default
    ram: 35%             # percentage of total cluster RAM quota for this bucket
    storage: magma       # magma or couchstore
    eviction: fullEviction
    replica: 1           # number of replicas
    compression: active  # off, passive, active
    historyretentionbytes: 2147483648  # CDC / history retention
    enableEncryptionAtRest: true
    rank: 3              # priority during provisioning
```

### Users

```yaml
users:
  - name: default
    password: password
    roles: admin
    auth_domain: local   # local (built-in) or external (LDAP)
```

### Views and Design Documents

```yaml
ddocs:
  - name: scale
    views: stats, padd, array

views:
  - name: stats
    map: "if(doc.profile){ emit(meta.id, doc.ops_sec); }"
    reduce: "_stats"
```

---

## 7. Test File Design

A test file is a sequence of **actions** executed against a provisioned scope.

### Action Types

| Type | Description |
|---|---|
| `image` | Start a workload container |
| `template` | Include a reusable YAML template |
| `command` | Run a shell command inside a container |
| `wait` | Block until a condition is true |
| `section` | Iterate over a subset of data (e.g., one action per bucket) |

### Variable Substitution

Test files support Go template syntax for dynamic values:

| Variable | Description |
|---|---|
| `{{.Orchestrator}}` | The Couchbase orchestrator node address |
| `{{.Bucket}}` | Current bucket name (in section loops) |
| `{{.Scale N}}` | N multiplied by the configured scale factor |
| `{{.AuthPassword}}` | RBAC created password |
| `{{.Nodes}}` | Comma-separated list of all cluster nodes |
| `{{.RestUsername}}` |  REST API username |
| `{{.RestPassword}}` |  REST API password |
| `{{.InActiveNode}}` |  Returns first inactive node |
| `{{.ActiveDataNode N}}` |  Returns Nth active data node in the cluster  |

### Example Action

```yaml
- image: sequoiatools/pillowfight
  command: "-U {{.Orchestrator}} -b {{.Bucket}} -I 100000 -t 4"
  wait: true
```

---

## 8. Provider Abstraction

The provider is selected in `config.yml`:

```yaml
provider: docker   # or: file, swarm, dev
```

### Docker Provider

The most common provider. It:
1. Pulls the Couchbase Docker image (e.g., `couchbase/server:7.6.0`)
2. Creates containers for each node defined in the scope
3. Maps ports from the container to the host (8091 → REST API, 11210 → data, etc.)
4. Creates a Docker network for inter-node communication
5. Calls the Couchbase REST API to initialize the cluster, add nodes, and rebalance

### File Provider

Used when you already have a Couchbase cluster running (e.g., physical lab machines, cloud VMs):
1. Reads server addresses from `hosts.json`
2. Skips container creation entirely
3. Connects via SSH and REST API
4. Runs test containers on the Docker host, pointing them at the remote cluster

### Dev Provider

For local development without Docker overhead:
- Uses a running `cluster-run` installation on the developer's machine
- No container lifecycle management
- Fastest iteration cycle for local development

---

## 9. Container Workloads

Every workload runs as a Docker container. Containers are organized in the `containers/` directory.

### KV and Load Generation

| Container | Purpose |
|---|---|
| `pillowfight` | Configurable KV workload using libcouchbase SDK |
| `gideon` | Document mutation tool (create, update, delete patterns) |
| `catapult` | High-throughput document loader for scale testing |
| `magmaloader` | Bulk loader optimized for Magma storage engine |

### Benchmarks

| Container | Purpose |
|---|---|
| `ycsb` | Yahoo! Cloud Serving Benchmark — read-heavy, write-heavy, mixed workloads |
| `tpcc` | TPC-C OLTP benchmark for transaction processing |
| `vegeta` | HTTP load testing for REST/API endpoints |
| `cbindexperf` | GSI index performance benchmarking |

### Query and Index

| Container | Purpose |
|---|---|
| `query_manager` | Creates/deletes N1QL indexes, executes queries |
| `indexmanager` | Manages GSI indexes lifecycle |
| `ftsindexmanager` | Manages FTS indexes (including vector search) |
| `analytics` | Runs Couchbase Analytics (CBAS) queries |
| `analyticsmanager` | Creates Analytics datasets and views |
| `cbq` | Interactive N1QL shell (for ad-hoc queries) |

### Test Frameworks

| Container | Purpose |
|---|---|
| `testrunner` | Python-based Couchbase test framework (submodule) |
| `perfrunner` | Python-based performance test framework |
| `sdk` | SDK-level tests (Java, Python, Go, .NET, etc.) |

### Service Management

| Container | Purpose |
|---|---|
| `eventing` | Deploy and execute JavaScript Eventing functions |
| `xdcr` | Set up and manage XDCR replication |
| `cbbackupmgr` | Backup and restore testing |
| `collections` | Collections and scopes management |
| `couchbase-cli` | Versioned CLI tool containers |

---

## 10. Data Flow

### Infrastructure Provisioning Flow

```
config.yml
  ↓ Parse CLI flags (lib/flags.go)
  ↓ Create ContainerManager (lib/container.go)
  ↓ Read scope YAML (lib/scope.go)
  ↓ Create Provider (lib/provider.go)
  ↓ ProvideCouchbaseServers()
      ↓ Create Docker containers (one per node)
      ↓ Wait for REST API on port 8091
      ↓ Initialize cluster via REST
      ↓ Add nodes and rebalance
      ↓ Create buckets via REST
      ↓ Create users via REST
      ↓ Configure FTS / Eventing / Analytics settings
  ↓ Store provisioned Scope object
```

### Test Execution Flow

```
test YAML
  ↓ Parse actions (lib/test.go)
  ↓ Resolve template includes
  ↓ For each action:
      ↓ Expand {{ }} variables using Scope data
      ↓ Dispatch:
          - container action → start Docker container
          - REST action      → call Couchbase REST API
          - wait action      → poll until condition met
          - template action  → expand and re-process recursively
          - section action   → repeat per-bucket / per-node
  ↓ Collect pass/fail results
  ↓ Write logs/results.tap4j
  ↓ Clean up containers and networks
```

---

## 11. Networking

### Container Networking Model

Sequoia creates a **custom Docker bridge network** for each test run. All Couchbase server containers and workload containers are attached to this network.

- Containers communicate by container name (Docker DNS)
- Port mappings expose services to the host machine for external access
- Network is torn down after the test completes

### Standard Port Assignments

| Port | Service |
|---|---|
| 8091 | Couchbase REST API (admin) |
| 11210 | Couchbase data service (SDK) |
| 8093 | N1QL Query service |
| 8094 | Full Text Search (FTS) service |
| 8095 | Analytics (CBAS) service |
| 8096 | Eventing service |
| 30000 | Sequoia debug (pprof) |

### Host Serialization

When containers need to reference cluster nodes by address, `lib/hostserializer.go` maps container names to their internal IP addresses and writes a `hosts.json` file that workload containers can consume.

---

## 12. Error Handling Strategy

### During Provisioning

- **Container startup failures**: Sequoia retries with exponential backoff and times out with a clear error if the container never becomes healthy.
- **REST API failures**: Errors are logged. Optional services (e.g., FTS if no FTS nodes are defined) are skipped gracefully.
- **Cluster initialization failures**: Fatal — provisioning stops and an error is reported.

### During Test Execution

- **Container workload failures**: Captured and recorded in TAP4J results. By default, execution continues to the next action.
- **Wait condition timeouts**: If a `wait` action times out, the test action is marked as failed but the test run continues unless explicitly configured to stop.
- **Template parse errors**: Fatal — test execution stops immediately.

### Result Reporting

All results are written to `logs/results.tap4j` in TAP4J XML format. A summary of pass/fail counts is printed to stdout on completion.

---

## 13. Extension Points

### Adding a New Provider

1. Create a new struct implementing the `Provider` interface in `lib/provider.go`
2. Add the provider name to the `NewProvider()` switch statement in `lib/provider.go`
3. Add any provider-specific configuration fields to `lib/spec.go`

### Adding a New Workload Container

1. Create a `Dockerfile` in `containers/<workload-name>/`
2. Add the build step to `build.sh`
3. Push the image to `sequoiatools/<workload-name>` on Docker Hub
4. Reference the image in test YAML files: `image: sequoiatools/<workload-name>`

### Adding a New Test Template

1. Create a YAML file in `tests/templates/<template-name>.yml`
2. Use the same action syntax as regular test files
3. Reference the template in tests: `template: tests/templates/<template-name>.yml`

### Adding New Scope Fields

1. Add the field to the appropriate spec struct in `lib/spec.go`
2. Handle the field in `lib/scope.go` provisioning logic
3. Map the field to a Couchbase REST API call in `lib/rest.go` if needed

---

## 14. Design Decisions and Trade-offs

### Why YAML for configuration?

YAML is human-readable and widely understood. Since scope and test files are the primary interface for test authors (not Go developers), readability was prioritized over strict type safety. The trade-off is that YAML errors are only caught at runtime.

### Why Docker for workloads?

Docker ensures that every workload runs in exactly the same environment regardless of the host OS. The trade-off is added complexity when debugging — you need to inspect container logs rather than just process output.

### Why TAP4J for results?

TAP4J (Test Anything Protocol for JUnit) is compatible with most CI systems (Jenkins, GitHub Actions, etc.). The framework emits TAP4J so test results can be imported directly into dashboards without post-processing.

### Why Go for the framework itself?

Go compiles to a single static binary with no runtime dependencies. Sequoia can be distributed and run on any Linux/macOS machine without installing a language runtime. The concurrency model (goroutines) also makes it easy to manage many containers in parallel.

### Sequential vs. Concurrent Actions

Actions are sequential by default to keep test logic easy to reason about. Concurrency is opt-in, controlled by the `concurrency` field on an action. This reduces the risk of race conditions in tests.

### Provider Abstraction Cost

The provider interface adds indirection and a small amount of boilerplate. The payoff is that the same test suite can run against Docker, real hardware, and Swarm without any changes to scope or test files — a significant benefit for organizations with varied infrastructure.

---

## Appendix: File Structure Reference

```
sequoia/
├── run.go                    # Main entry point
├── config.yml                # Runtime configuration (provider, scope, test)
├── build.sh                  # Builds all workload containers
├── go.mod                    # Go module definition
│
├── lib/                      # Core framework library
│   ├── flags.go              # CLI flag parsing
│   ├── container.go          # Docker container lifecycle management
│   ├── provider.go           # Provider interface and implementations
│   ├── scope.go              # Infrastructure provisioning
│   ├── test.go               # Test execution engine
│   ├── rest.go               # Couchbase REST API client
│   ├── spec.go               # YAML spec data structures
│   ├── template.go           # Go template rendering
│   ├── common.go             # Shared utilities
│   └── hostserializer.go     # Host-to-IP mapping
│
├── containers/               # Workload container Dockerfiles
│   ├── pillowfight/          # KV workload
│   ├── ycsb/                 # YCSB benchmark
│   ├── testrunner/           # Python test framework
│   ├── ftsindexmanager/      # FTS index management
│   ├── eventing/             # Eventing functions
│   └── ...
│
├── tests/                    # Test and scope YAML files
│   ├── templates/            # Reusable test snippets
│   ├── simple/               # Simple smoke tests
│   ├── integration/          # Full integration test suites
│   │   └── 8.0/              # Version-specific tests
│   ├── 2i/                   # Secondary index tests
│   ├── n1ql/                 # Query tests
│   ├── fts/                  # Full-text search tests
│   ├── analytics/            # Analytics tests
│   ├── eventing/             # Eventing tests
│   ├── xdcr/                 # Cross-datacenter replication tests
│   └── ...
│
├── docs/                     # Documentation
│   ├── design.md             # This document
│   ├── architecture.agents.md
│   └── agent-context/
│       ├── domain-glossary.md
│       ├── repo-inventory.md
│       ├── build-test-matrix.md
│       └── troubleshooting.md
│
└── logs/                     # Output: results.tap4j, debug logs
```

---

*For questions about the architecture, refer to `docs/architecture.agents.md`. For terminology, see `docs/agent-context/domain-glossary.md`.*

# lib/ — Core Framework Package

Package `sequoia`. All files compile into a single package imported by `run.go` (package main).

## Files

### spec.go
YAML-to-Go struct mapping. Defines all data structures that scope and test YAML files deserialize into.

Key types:
- `BucketSpec` — bucket config: name, ram, replica, type (couchbase/ephemeral/memcached), eviction, storage (magma/couchbase), TTL, compression, history retention, encryption, rank, conflict resolution, throttle settings
- `ServerSpec` — cluster node config: count, RAM, services, ports, credentials, index/analytics paths, encryption
- `ScopeSpec` — top-level container holding `[]ServerSpec`, `[]BucketSpec`, `[]RbacSpec`, ddocs, views, sync gateways
- `DDocSpec` / `ViewSpec` — design document and view definitions
- `SyncGatewaySpec` / `AccelSpec` / `LoadBalancerSpec` — mobile and edge infrastructure specs

Key functions:
- `NewScopeSpec(fileName)` / `SpecFromYaml(fileName)` — load and configure a scope YAML
- `ConfigureSpec(spec)` — expand name patterns, set defaults, resolve service counts
- `ApplyToServers(op, start, end)` / `ApplyToAllServers(op)` — iterate server specs and run an operation closure
- `SetYamlSpecDefaults(spec)` — fill in missing port/credential defaults

---

### scope.go
Cluster lifecycle orchestration. `Scope` is the central runtime object passed through setup and teardown.

Key type: `Scope` — holds `ScopeSpec`, `Provider`, `RestClient`, `ContainerManager`, `TestFlags`, `Version`, `Loops`, `Vars`

Setup pipeline (called in order by `SetupServer()`):
1. `WaitForServers()` — poll REST until nodes respond
2. `InitCli()` — run `couchbase-cli` init container
3. `InitNodes()` — set data/index/analytics paths, configure node services
4. `InitCluster()` — form cluster, set RAM quotas per service
5. `AddUsers()` — create RBAC users
6. `AddNodes()` — add remaining nodes to cluster
7. `RebalanceClusters()` — trigger rebalance, wait for completion
8. `ApplyInternalSettings()` — POST to `/internalSettings` (e.g. `magmaMinMemoryQuota`)
9. `CreateBuckets()` — `bucket-create` per bucket spec, including optional flags: eviction, compression, TTL, storage, durability, history retention, encryption, rank, conflict resolution, vbuckets
10. `CreateScope()` — create named scopes and collections via REST API

Other methods:
- `Teardown()` — remove containers
- `CompileCommand(actionCommand)` — render Go template string against current scope
- `GetCliImage()` — resolve versioned CLI image tag
- `SetVarsKV(key, id)` / `GetVarsKV(key)` — scope-level key/value store for container alias IDs
- `DeleteBuckets()` / `RemoveNodes()` — teardown helpers
- `EnableClientCertAuth()` / `EnableLogAndConfigEncryption()` / `CreateEncryptionKeys()` — security setup

---

### test.go
Test execution engine. Reads action YAML, resolves templates, and drives container runs.

Key types:
- `ActionSpec` — one entry in a test YAML: image, command, wait, async, duration, repeat, until, before, requires, alias, section_start/end, client op
- `ClientActionSpec` — exec/cp/kill/rm against an already-running container
- `TemplateSpec` — included template file reference
- `Test` — holds actions, results, TAP writer, concurrency state

Key functions:
- `ActionsFromFile(fileName)` — parse a test YAML into `[]ActionSpec`
- `Test.Run(scope)` — main loop: iterate actions, resolve templates, launch containers
- `runActions(scope, loop, actions)` — per-loop action execution with concurrency, wait, duration, and section filtering
- `ResolveTemplateActions(scope, action)` — expand `template:` references with positional `$0 $1 $2` args
- `CacheIncludedTemplate(scope, specs)` — load `include:` files into template cache
- `runTask(scope, task, action)` — submit a `ContainerTask` and handle alias, wait, async
- `WatchErrorChan(echan, n, scope, expectError)` — collect and log container exit results
- `CollectInfo(scope)` — gather cbcollect logs on failure

---

### template.go
Go template resolver. All `command:` strings in test YAML are rendered through `ParseTemplate()` before being passed to Docker.

Key type: `TemplateResolver` — wraps `*Scope`, exposes all template functions as methods

**Scaling:**
- `Scale(val int) string` — `val × -scale flag` (minimum 1)
- `RandomScale(args ...int) string` — random int in `[min, max]`; defaults: min=500, max=1000

**Node selectors:**
- `Orchestrator()` — first node IP of cluster 0
- `NthDataNode(n)`, `ActiveDataNode(n)`, `InActiveNode()`, `NthInActiveNode(n)`
- `IndexNode()`, `ActiveIndexNode(n)`, `NthIndexNode(n)`, `LastIndexNode()`
- `QueryNode()`, `NthQueryNode(n)`, `ActiveQueryNode(n)`
- `FTSNode()`, `NthFTSNode(n)`, `FTSNodePort()`
- `EventingNode()`, `NthEventingNode(n)`, `ActiveEventingNode(n)`
- `AnalyticsNode()`, `NthAnalyticsNode(n)`, `ActiveAnalyticsNode(n)`
- `BackupNode()`, `NthBackupNode(n)`
- `Nodes()`, `Cluster(index, servers)`, `ClusterNodes()`, `Service(service, servers)`

**Bucket / auth:**
- `Bucket()` — first bucket name
- `NthBucket(n)` — nth bucket (0-indexed)
- `RestUsername()`, `RestPassword()`, `AuthUser()`, `AuthPassword()`

**Control flow:**
- `DoOnce() bool` — true only on loop 0
- `Loop() int` — current loop counter
- `EvenCount()` / `OddCount()`
- `Version() float64` — server version as float (e.g. `7.6`)

**Utilities:**
- `TailLogs(key, tail)` / `AllLogs(key)` — read container output by alias
- `NoPort(addr)` — strip `:port` suffix
- `ToJson(data)`, `ToDoubleQuotes(data)`, `WrapSingleQuote(data)`
- `StrList(args...)`, `MkRange(args...)`, `FloatToInt(v)`, `StrToInt(v)`
- `ContainerIP(alias)` — resolve alias to container IP

**Template functions (pipeline-style, registered in `ParseTemplate`):**
`net`, `bucket`, `noport`, `json`, `strlist`, `mkrange`, `contains`, `excludes`, `tolist`, `ftoint`, `strtoint`, `last`, `to_ip`, `active`, `auth_user`, `to_double_quote`, `wrap_single_quote`

---

### provider.go
Infrastructure abstraction. `Provider` interface decouples cluster provisioning from the rest of the framework.

Interface:
```go
type Provider interface {
    GetType() string
    GetHostAddress(name string) string
    GetRestUrl(name string) string
    ProvideCouchbaseServers(filename *string, servers []ServerSpec)
    ProvideSyncGateways(syncGateways []SyncGatewaySpec)
    ProvideAccels(accels []AccelSpec)
    ProvideLoadBalancer(loadBalancer LoadBalancerSpec)
}
```

Implementations:
- `DockerProvider` — spins up `sequoiatools/couchbase` containers; supports cpu/memory limits via `DockerProviderOpts`
- `SwarmProvider` — Docker Swarm services; `ProvideCouchbaseServer()` maps port offsets across zones
- `FileProvider` — reads `hosts.json`; no provisioning, just address lookup
- `ClusterRunProvider` — `dev:` mode; maps node names to localhost ports (9000, 9500…)

`NewProvider(flags, servers, ...)` — parses `-provider` flag and returns the right implementation.

---

### container.go
Docker client wrapper. All container lifecycle operations go through `ContainerManager`.

Key types:
- `ContainerTask` — image, command, binds, links, env, async, duration, concurrency
- `TaskResult` — exit status and pass/fail outcome
- `ContainerManager` — holds `[]*docker.Client` (one per swarm node), managed container list, image pull cache

Key methods:
- `Run(task)` — primary entry point: pull image if needed, create and start container, return ID and error channel
- `RunContainerTask(task)` — lower-level: build options, run, return result channel
- `WaitContainer(container, c)` — blocks until container exits, sends `TaskResult` to channel
- `ExecContainer(id, cmd, detach)` — `docker exec` against running container
- `RemoveContainer(id)` / `KillContainer(id)` / `RemoveManagedContainers(soft)`
- `PullImage(repo)` / `PullTaggedImage(repo, tag)` — pull with deduplication
- `GetLogs(ID, tail)` — fetch container stdout/stderr
- `RunRestContainer(cmd)` — run a one-shot `appropriate/curl` container and return stdout
- `SaveCouchbaseContainerLogs(logDir)` — copy `/var/log/couchbase` from server containers

---

### rest.go
REST API client for querying and configuring the Couchbase cluster at runtime.

Key type: `RestClient` — holds cluster specs, provider, container manager, and a TTL cache

Key methods:
- `GetServerVersion()` — query `/pools/default` for version string
- `NodeHasService(service, host)` — check if a node runs a given service (cached)
- `IsNodeActive(host)` — check node membership in cluster
- `GetMemTotal(host)` / `GetMemReserved(host)` / `GetIndexQuota(host)` — memory introspection
- `ClusterIsRebalancing(host)` — poll `/pools/default/rebalanceProgress`
- `WatchForTopologyChanges()` — background goroutine that resets cache on topology change
- `JsonRequest(auth, url, v)` / `JsonPostRequest(auth, url, data, v)` — generic REST helpers
- `updateNumberOfBucktes(n)` — POST `/internalSettings` `maxBucketCount`
- `updateMagmaMinMemoryQuota(quota)` — POST `/internalSettings` `magmaMinMemoryQuota`
- `createScope(bucket, scope)` — POST `/pools/default/buckets/{b}/scopes`
- `createCollections(bucket, scope, collection)` — POST to collections endpoint

---

### flags.go
CLI flag definitions and parsing.

Key type: `TestFlags` — all runtime configuration fields (provider, scope, test, scale, skip_setup, skip_teardown, repeat, etc.)

Key functions:
- `NewTestFlags()` — allocate with defaults
- `Parse()` — register flag sets (default, image, clean, testrunner), parse `os.Args`, call `SetFlagVals()`
- `SetFlagVals()` — copy parsed flag values into struct fields
- `AddDefaultFlags(fset)` — registers the core flags: `-provider`, `-scope`, `-test`, `-scale`, `-skip_setup`, `-skip_teardown`, `-repeat`, `-duration`, `-collect`, `-generate_xml`, etc.

---

### common.go
Shared utilities with no external dependencies beyond stdlib.

Key functions:
- `ExpandServerName(name, count, offset)` / `ExpandBucketName(...)` / `ExpandName(...)` — expand `cb` with count=3 → `[cb1, cb2, cb3]`
- `ReadYamlFile(filename, spec)` — unmarshal YAML file into any struct
- `DDocToJson(ddoc)` — serialize a `DDocSpec` to a Couchbase design document JSON string
- `RandStr(size)` / `RandHostStr(size)` — random string generators
- `ApplyFlagOverrides(overrides, opts)` — parse `key=value` string and set fields on a struct via reflection
- `BuildVolumes(volumes)` — parse volume mount strings into `[]string`
- `MakeTaskMsg(image, id, command, is_err)` — format container log prefix
- `ToCamelCase(s)` — convert underscore strings to CamelCase

---

### hostserializer.go
Generates `hosts.json` — the handoff format between a Docker run and a subsequent `file:` provider run.

- `GenerateMobileHostDefinition(scope)` — walk sync gateway and accel specs, write `hosts.json` with cluster, gateway, and accel addresses

---

## Adding a New Bucket Field

1. Add field to `BucketSpec` in `spec.go` with a `yaml:"..."` tag
2. Add an `if bucket.FieldName != ""` block in `CreateBuckets()` in `scope.go` appending the CLI flag
3. Set the field in the scope YAML under the relevant bucket entry

## Adding a New Template Function

1. Add a method on `TemplateResolver` in `template.go`
2. If it needs pipeline syntax (e.g. `| myFunc arg`), register it in the `netFunc` map inside `ParseTemplate()`
3. Method-style calls (`{{.MyFunc arg}}`) work automatically without registration

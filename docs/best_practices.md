# Sequoia — Best Practices

> Distilled from **1,538 Gerrit code reviews** conducted by the team over several years.  
> Last Updated: March 2026

---

## Table of Contents

1. [Code Hygiene](#1-code-hygiene)
2. [Logging](#2-logging)
3. [Error Handling](#3-error-handling)
4. [Test YAML Authoring](#4-test-yaml-authoring)
5. [Scope YAML Authoring](#5-scope-yaml-authoring)
6. [Container Development](#6-container-development)
7. [Python Coding Standards](#7-python-coding-standards)
8. [Go Coding Standards](#8-go-coding-standards)
9. [Security and Credentials](#9-security-and-credentials)
10. [Naming Conventions](#10-naming-conventions)
11. [Code Reuse and DRY](#11-code-reuse-and-dry)
12. [Validation and Verification](#12-validation-and-verification)
13. [Cluster Operations in Tests](#13-cluster-operations-in-tests)
14. [Performance and Reliability](#14-performance-and-reliability)
15. [Code Review Checklist](#15-code-review-checklist)

---

## 1. Code Hygiene

### Remove Commented-Out Code

Do **not** leave commented-out code in the codebase. If code is no longer needed, delete it. Version control (Git) preserves history — you can always recover it.

```python
# Bad — dead code left in
# scope_coll_map = self.get_all_scopes(bucket)
content = self.get_raw_collection_map(bucket)

# Good — clean, no dead code
content = self.get_raw_collection_map(bucket)
```

### Remove Debug Print Statements Before Merging

Stray `print()` calls used during development should be removed before submitting for review. Use the proper logging framework instead.

```python
# Bad
print("Will run this {}".format(command))

# Good
self.log.info("Will run this {}".format(command))
```

### Keep Comments Accurate

If a comment says "sleep for 600 minutes" but the code sleeps for 63 seconds, fix the discrepancy. Misleading comments are worse than no comments.

```yaml
# Bad — comment says 10 minutes, code says 63 seconds
# Sleep for some more time after projector-kill completes (10 minutes)
- image: sequoiatools/cmd
  entrypoint: sleep
  command: "63"

# Good — comment matches the code
# Sleep for ~1 minute after projector-kill completes
- image: sequoiatools/cmd
  entrypoint: sleep
  command: "63"
```

### Clean Up TODO Items

When a TODO is completed, remove the TODO comment. Stale TODOs create confusion about what work remains.

---

## 2. Logging

### Use the Logger, Not `print()`

All container scripts should use `self.log.info()`, `self.log.error()`, etc. instead of `print()`. Output from `print()` may not be captured in Docker logs, making debugging impossible in CI runs.

```python
# Bad — print won't be retained in Docker logs
print(f"Current Resident Ratios of Index nodes - {index_rr}")

# Good — logger output appears in docker logs
self.log.info(f"Current Resident Ratios of Index nodes - {index_rr}")
```

### Log at the Right Level

| Level | Use for |
|---|---|
| `self.log.debug()` | Verbose data dumps (index maps, full query lists) |
| `self.log.info()` | Normal operational messages (action started, completed) |
| `self.log.error()` | Failures that need attention |

### Add Meaningful Log Messages

Log messages should tell you *what* is happening and *with what data*. Include relevant context.

```python
# Bad — vague
self.log.info("Starting")

# Good — actionable context
self.log.info(f"Starting to create {max_num_idx} indexes on collections: {keyspace_name_list}")
```

### Differentiate Method Descriptions

When two methods do similar things, make their docstrings distinct so developers (and logs) can tell them apart.

```python
# Bad — both methods have identical summaries
def get_index_map(...):
    """Return the index map for the specified bucket"""

def get_stats_map(...):
    """Return the index map for the specified bucket"""  # copy-paste error!

# Good — each method describes its unique purpose
def get_index_map(...):
    """Return the index-to-storage mapping for the specified bucket"""

def get_stats_map(...):
    """Return the stats counters for each index on the specified node"""
```

---

## 3. Error Handling

### Initialize Status to FAIL

When writing tests that report a pass/fail status, always initialize the status to `"FAIL"`. Only set it to `"PASS"` when all checks succeed. This ensures that if the test errors out or crashes, the result defaults to failure rather than a false positive.

```python
# Bad — status defaults to pass; a crash = false positive
status = "PASS"
try:
    run_checks()
except Exception:
    status = "FAIL"

# Good — status starts as fail; only set to pass on success
status = "FAIL"
run_checks()
if all_checks_passed:
    status = "PASS"
```

### Avoid Unguarded Infinite Loops

Any `while` loop waiting for a condition must have a timeout or a maximum iteration counter. Without one, a test can hang forever in CI.

```python
# Bad — infinite loop risk
while composite_status != app_status:
    time.sleep(10)
    composite_status = get_status()

# Good — bounded loop with timeout
max_retries = 60
for attempt in range(max_retries):
    composite_status = get_status()
    if composite_status == app_status:
        break
    time.sleep(10)
else:
    raise TimeoutError(f"Status did not reach {app_status} after {max_retries} attempts")
```

### Handle Exceptions Meaningfully

When raising exceptions, include context about what went wrong. When catching exceptions, decide whether to retry, log, or re-raise — don't silently swallow them.

```python
# Bad — bare except, swallows everything
try:
    return service_nodes[0]
except:
    pass

# Good — specific exception, informative message
try:
    return service_nodes[0]
except IndexError:
    raise Exception("Service node list is empty — no nodes found for the requested service")
```

### Use `defer` for Cleanup in Go

When generating reports or cleaning up resources in Go, use `defer` with closures to ensure the cleanup runs even if a panic occurs during test execution.

```go
// Good — deferred cleanup runs even on panic
defer func() {
    writeXMLReport(cases_run_list, total_duration)
}()
```

### Raise Exceptions on Build/Index Failures

If all indexes were not built within the timeout, raise an exception so the test is marked as failed. Silent failures lead to false positives.

```python
if not all_indexes_built:
    raise Exception(f"All indexes were not built after {timeout} seconds")
```

---

## 4. Test YAML Authoring

### Use Unique Section Names

Every `section_start` / `section_end` pair must have a unique name. Duplicate section names cause ambiguity when tests reference sections by name.

```yaml
# Bad — reused section name
- section_start: query_after_rebalance
  ...
- section_end: query_after_rebalance

- section_start: query_after_rebalance    # duplicate!

# Good — distinct section names
- section_start: query_after_swap_rebalance
- section_start: query_after_failover_rebalance
```

### Add Comments Before Major Steps

Add a descriptive comment before each logical block in a test file. This dramatically improves readability for anyone maintaining the test later.

```yaml
# Good — clear section boundaries
# creating eventing handlers and deploying them
- test: tests/eventing/test_eventing_rebalance_integration_timers.yml
  section: create_and_deploy

# creating datasets and indexes for analytics
- test: tests/analytics/test_analytics_integration.yml
  section: analytics_setup
```

### Use Accurate Terminology in Comments

Use the correct Couchbase terminology: "pause" and "resume" for eventing handlers — not "undeploy" and "redeploy" (which mean something different).

```yaml
# Bad — wrong terminology
############### undeploy functions ################

# Good — correct terminology
############### pause eventing functions ################
```

### Apply Operations to All Required Buckets

When a test creates multiple buckets, ensure that operations like data loading, index creation, and query execution cover **all** relevant buckets — not just the first one.

```yaml
# Bad — only operates on bucket 0
- image: sequoiatools/indexmanager
  command: "-n {{.Orchestrator}} -o {{.RestPort}} ... -b {{.Bucket}} -a create_index"

# Good — covers all buckets
- image: sequoiatools/indexmanager
  command: "-n {{.Orchestrator}} -o {{.RestPort}} ... -b {{.Bucket}} -a create_index"
  wait: true
- command: "-n {{.Orchestrator}} -o {{.RestPort}} ... -b {{.NthBucket 1}} -a create_index"
  wait: true
- command: "-n {{.Orchestrator}} -o {{.RestPort}} ... -b {{.NthBucket 2}} -a create_index"
  wait: true
```

### Use Template Variables Instead of Hardcoded Values

Never hardcode usernames, passwords, or ports. Use the template variables provided by Sequoia.

```yaml
# Bad — hardcoded credentials and port
command: "-i {{.Orchestrator}}:8091 -u Administrator -p password"

# Good — uses template variables
command: "-i {{.Orchestrator}}:{{.RestPort}} -u {{.RestUsername}} -p {{.RestPassword}}"
```

### Validate After Cluster Operations

After any topology change (rebalance, failover, swap), add a validation step to confirm that all indexes exist and data is consistent.

```yaml
# Good — validate indexes exist after rebalance
- template: rebalance_swap
  args: "{{.InActiveNode}}, {{.ActiveIndexNode 0}}, index"
  wait: true

- image: sequoiatools/indexmanager
  command: "-n {{.Orchestrator}} ... -a item_count_check --sample_size 10"
  wait: true
```

### Wait for Dependent Operations

When starting an operation that depends on a previous one completing (e.g., queries after rebalance), use `wait: true` on the dependency.

```yaml
# Bad — rebalance may still be running when queries start
- template: rebalance
- template: run_queries

# Good — queries start only after rebalance completes
- template: rebalance
  wait: true
- template: run_queries
```

### Check Range Boundaries in Loops

When using `mkrange` in `foreach` loops, double-check the start and end values match the number of items (buckets, scopes, collections) you intend to cover.

```yaml
# Bad — range 0-9 creates 10 items, but only 9 collections exist (0-8)
foreach: "{{range $i, $sc := mkrange 0 9}}"

# Good — range matches available items
foreach: "{{range $i, $sc := mkrange 0 8}}"
```

### Build Indexes Incrementally to Avoid OOM

When creating large numbers of indexes (e.g., 800+), add item count checks between batches. Building all indexes at once can lead to out-of-memory issues.

---

## 5. Scope YAML Authoring

### Name Buckets Sequentially

Bucket names should be sequential and predictable. If you have `bucket4`, the next one should be `bucket5`, not a duplicate or skip.

```yaml
# Bad — bucket5 missing, bucket4 duplicated
- name: bucket4
  ram: 8%
- name: bucket4    # duplicate!
  ram: 8%

# Good — sequential naming
- name: bucket4
  ram: 8%
- name: bucket5
  ram: 8%
```

### Use Enough Nodes for the Test Scenario

Size the cluster appropriately for the operations you plan to perform. For example, if you plan 3 failovers, you need at least 7 nodes (4 remaining to maintain quorum).

### Match Users to Buckets

When specifying `users:` in a server block, ensure the user list matches the bucket list for proper RBAC setup.

### Set Up Enough Replications for XDCR

For XDCR testing, create one replication per bucket. Don't replicate only the default bucket when multiple buckets exist.

---

## 6. Container Development

### Follow the Dockerfile Naming Convention

The file must be named `Dockerfile` with a capital `D`. Lowercase `dockerfile` breaks some Docker tooling and CI systems.

```
#  Bad
containers/my_tool/dockerfile

# Good
containers/my_tool/Dockerfile
```

### Don't Depend on External Services in Tests

Avoid calling external URLs (public websites, external APIs) from within test containers. If the external service goes down, your test fails for reasons unrelated to Couchbase.

```python
# Bad — test depends on an external website being up
"hostname": "http://qa.sc.couchbase.com/"

# Good — use internal cluster endpoints or mock services
"hostname": "http://{{.Orchestrator}}:8091/"
```

### Keep Containers Focused

Each container should do **one thing well**. Don't merge unrelated functionality into a single container. If N1QL and Analytics workloads need different implementations, split them into separate containers.

### Merge Feature Branches Before Referencing

When a Dockerfile clones a Git repository on a specific branch, ensure that branch will be merged to main. Stale branches create maintenance burden.

```dockerfile
# Bad — references a feature branch that may never merge
RUN git clone -b javaClientMigrationTo3.3 https://github.com/couchbaselabs/AnalyticsQueryApp.git

# Good — references main/master or a stable release tag
RUN git clone -b main https://github.com/couchbaselabs/AnalyticsQueryApp.git
```

### Parameterize Branches in Containers

When checking out external repos in Dockerfiles or scripts, allow the branch to be passed as a parameter rather than hardcoding it.

---

## 7. Python Coding Standards

### Prefer f-Strings Over `.format()` (in Python 3)

For containers that use Python 3, prefer f-strings for readability and consistency. For containers that still use Python 2.7, `.format()` is the only option.

```python
# Bad (in Python 3 code) — old-style formatting
endpoint = "{}://{}:{}/stats".format(self.scheme, index_node_addr, self.node_port_index)

# Good (Python 3)
endpoint = f"{self.scheme}://{index_node_addr}:{self.node_port_index}/stats"

# ✅ Also acceptable (Python 2.7 containers)
endpoint = "{}://{}:{}/stats".format(self.scheme, index_node_addr, self.node_port_index)
```

**Know your container's Python version before choosing a string formatting style.**

### Use `argparse` Over `optparse`

For new containers, use `argparse` (Python standard library). `optparse` is deprecated since Python 3.2.

### Avoid Bare `except:` Clauses

Always catch specific exceptions. Bare `except:` catches everything, including `KeyboardInterrupt` and `SystemExit`, making debugging difficult.

```python
# Bad
except:
    raise Exception("service node list is empty")

# Good
except IndexError:
    raise Exception("service node list is empty")
```

### Don't Duplicate Utility Methods

If a helper method (e.g., `get_nodes_from_service_map()`) is needed in multiple places, define it once in a shared location and import it. Don't copy-paste it into every container.

### Verify Parameters Before Adding New Ones

Before adding a new CLI argument to a container, check if an existing argument already covers the same functionality. Unnecessary arguments increase maintenance burden.

---

## 8. Go Coding Standards

### Align Struct Fields

In Go struct definitions, align field names and types for readability.

```go
// Bad — misaligned
type TestFlags struct {
    Capella *bool `yaml:"capella"`
    TLS              *bool `yaml:"tls"`

// Good — aligned
type TestFlags struct {
    Capella          *bool `yaml:"capella"`
    TLS              *bool `yaml:"tls"`
```

### Remove Commented Code in Go

Same rule as Python — remove commented-out code. Don't leave old function calls or dead conditions in the source.

### Use `defer` for Panic-Safe Cleanup

Place `defer` calls for report generation and cleanup **before** the code that might panic, so cleanup always runs.

```go
// Bad — defer placed after test execution; panic skips it
runTests()
defer writeReport()  // never reached if runTests panics

// Good — defer placed before test execution
defer func() {
    writeReport(results)
}()
runTests()
```

### Use Closures with `defer` When Variables Change

If a deferred function references a variable whose value changes after the defer, use a closure to capture the final value.

---

## 9. Security and Credentials

### Never Hardcode Credentials in README or Docs

Use placeholder strings like `<username>` and `<password>` in documentation and examples.

```markdown
# Bad
python script.py -u Administrator -p password

# Good
python script.py -u <username> -p <password>
```

### Don't Embed Credentials in Container JSON Configs

Eventing handler configurations and similar JSON files should not contain hardcoded RBAC credentials. These should be parameterized.

### Use TLS/Secure Flags Consistently

Containers should support a `--tls` or `--capella` flag to switch between HTTP and HTTPS. Don't hardcode port 8091 when a TLS run needs port 18091.

---

## 10. Naming Conventions

### Index Names Must Be Unique

When defining index templates, ensure each index has a unique name. Duplicate index names cause silent creation failures.

```python
# Bad — duplicate index names
{"indexname": "idxvector1", ...},
{"indexname": "idxvector1", ...},  # duplicate!

# Good — unique names
{"indexname": "idxvector1", ...},
{"indexname": "idxvector2", ...},
```

### Use Descriptive File and Method Names

New files should have a clear purpose evident from the name. If a file's purpose isn't obvious, add a docstring at the top.

### Use `CREATE OR REPLACE` for Resilience

When creating functions (UDFs), use `CREATE OR REPLACE` so the statement is idempotent and can be re-run safely.

```sql
-- Bad — fails if function already exists
CREATE FUNCTION run_n1ql_query(bucketname) LANGUAGE JAVASCRIPT AS ...

-- Good — idempotent
CREATE OR REPLACE FUNCTION run_n1ql_query(bucketname) LANGUAGE JAVASCRIPT AS ...
```

---

## 11. Code Reuse and DRY

### Don't Duplicate Logic Across Files

If two files share substantial logic, refactor the common code into a shared module or extend the existing method. Repetitive code across files is a maintenance nightmare.

### Use Templates for Repeated Test Patterns

If the same sequence of actions appears in multiple test files, extract it into a template under `tests/templates/`.

### Extend Existing Methods Instead of Adding New Ones

Before adding a new action/method, check if the existing one can be parameterized to handle the new case.

### Move Shared Container Logic to Common Files

When the same helper function appears in multiple containers (e.g., `get_nodes_from_service_map`), extract it into a shared utility that can be imported.

---

## 12. Validation and Verification

### Add Item Count Checks After Data Operations

After loading data or performing cluster operations, add an item count check to verify data integrity.

```yaml
- image: sequoiatools/indexmanager
  command: "-n {{.Orchestrator}} ... -a item_count_check --sample_size 10"
  wait: true
```

### Validate Index Builds Instead of Using Sleep

Instead of sleeping for a fixed time and hoping indexes are built, use the `wait_for_idx_build_complete` container to actively poll.

```yaml
# Bad — arbitrary sleep, may be too short or too long
- image: sequoiatools/cmd
  entrypoint: sleep
  command: "1200"
  wait: true

# Good — actively polls until indexes are built
- image: sequoiatools/wait_for_idx_build_complete
  command: "{{.ActiveIndexNode 0}} {{.RestUsername}} {{.RestPassword}}"
  wait: true
```

### Use Averages for Metric Checks

When checking metrics like Resident Ratio, use an average over a time window (e.g., 5 minutes) instead of a single point-in-time check. Metrics fluctuate, and a single check can give misleading results.

### Validate at Multiple Points

Don't just validate at the end of a test. Add validation checkpoints after each major cluster operation (rebalance, failover, swap).

---

## 13. Cluster Operations in Tests

### Wait Between Failovers for Auto-Failover

When testing auto-failover with multiple nodes, you must wait between stopping each node. Auto-failover will not initiate if multiple nodes go down simultaneously.

```yaml
# Bad — all nodes stopped at once
- command: "/cbinit.py {{.Nodes | net 3}} root couchbase stop"
- command: "/cbinit.py {{.Nodes | net 4}} root couchbase stop"
- command: "/cbinit.py {{.Nodes | net 5}} root couchbase stop"

# Good — wait between each stop for auto-failover to trigger
- command: "/cbinit.py {{.Nodes | net 3}} root couchbase stop"
  wait: true
- image: sequoiatools/cmd
  entrypoint: sleep
  command: "120"
  wait: true
- command: "/cbinit.py {{.Nodes | net 4}} root couchbase stop"
  wait: true
```

### Bring Back All Failed-Over Nodes

After testing failover scenarios, bring back **all** the nodes that were stopped and rebalance them into the cluster.

### Use Delta Recovery After Failover

When bringing failed-over nodes back, perform delta recovery before rebalance to avoid full data resync.

### Include All Required Flags in CLI Commands

When using `couchbase-cli`, ensure all required flags are present. For example, `setting-autofailover` requires `--enable-auto-failover=1` along with other flags.

### Combine Sequential Rebalances

If two rebalance operations can be combined into one (e.g., adding two nodes), do it to save test execution time.

### Add Collection CRUD During Topology Changes

For integration and longevity tests, perform collection create/drop operations during rebalances and failovers. Most KV bugs are found in scenarios combining collection CRUD with topology changes.

### Add Durability Workloads in Collection Tests

Include durability-level document loading in collection tests. Many KV bugs were specific to durability + collection scenarios.

---

## 14. Performance and Reliability

### Roll Out New Features Gradually

When adding new framework features (e.g., XML report generation), default them to `off` initially. Run a few full system test cycles to validate before turning them on by default.

### Don't Build All Indexes at Once

In large-scale tests, build indexes in batches with item count checks in between to avoid OOM conditions.

### Use `wait_for_idx_build_complete` at Multiple Points

Add this container at multiple points in the test with different indexer nodes, not just once at the end.

### Parameterize Scale-Sensitive Values

Data volumes, document counts, and sleep durations should use `{{.Scale N}}` so they adjust based on the test environment size.

---

## 15. Code Review Checklist

Use this checklist when submitting or reviewing changes:

### Before Submitting

- [ ] No commented-out code left in the change
- [ ] No `print()` statements — use `self.log` instead
- [ ] All comments match what the code actually does
- [ ] Completed TODO items have been removed
- [ ] All section names are unique in test YAML files
- [ ] Range boundaries in `foreach` loops match the actual item count
- [ ] Operations are applied to all relevant buckets (not just the default)
- [ ] Template variables used for credentials and ports (no hardcoding)
- [ ] Validation steps added after cluster operations
- [ ] `wait: true` used for operations that must complete before the next step
- [ ] Error status initialized to `FAIL` (not `PASS`)
- [ ] All loops have a timeout or max-retry counter
- [ ] Dockerfile named with capital `D`
- [ ] No dependencies on external services/URLs
- [ ] Index names are unique
- [ ] f-strings used in Python 3 containers; `.format()` used in Python 2.7 containers

### During Review

- [ ] Is there duplicated logic that should be refactored?
- [ ] Can an existing method be extended instead of adding a new one?
- [ ] Are new arguments necessary, or can existing ones handle the case?
- [ ] Is the container doing one thing well, or is it accumulating unrelated features?
- [ ] Are feature branches in Dockerfiles planned for merge?
- [ ] Is the test doing enough validation (item counts, index existence)?
- [ ] Are failover tests waiting between failures and bringing nodes back?

---

*This document is a living guide. Update it as new patterns and anti-patterns emerge from code reviews.*

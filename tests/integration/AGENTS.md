# Integration Tests — Overview

This directory contains multi-service integration tests for Couchbase Server, organized by release era. Each sub-folder has its own `AGENTS.md` with full scope and test workflow documentation. The files directly in this directory (loose `scope_*.yml` and `test_*.yml`) are older pre-series tests that pre-date the sub-folder organization.

---

## Sub-Folder Index

| Folder | Era | Storage | Key Features | AGENTS.md |
|--------|-----|---------|-------------|-----------|
| [`cheshirecat/`](cheshirecat/AGENTS.md) | Earliest | Couchstore | Cumulative service addition pattern; longevity tests; 3 scope variants; eventing-specific bucket naming scheme | [cheshirecat/AGENTS.md](cheshirecat/AGENTS.md) |
| [`neo/`](neo/AGENTS.md) | Pre-7.2 | Magma + Couchstore + Hybrid | Multiple storage variants; milestone decomposition; audit logging; 8-node remote cluster | [neo/AGENTS.md](neo/AGENTS.md) |
| [`7.2/`](7.2/AGENTS.md) | 7.2 | Magma | Baseline versioned series; no history retention; no shard affinity; CLI `couchbase-cli:7.2` | [7.2/AGENTS.md](7.2/AGENTS.md) |
| [`7.6/`](7.6/AGENTS.md) | 7.6 | Magma | Adds shard affinity, history retention, bucket rank; alternate 25-node cluster scope | [7.6/AGENTS.md](7.6/AGENTS.md) |
| [`7.7/`](7.7/AGENTS.md) | 7.7 | Magma | Adds `bucket10` for composite + vector (L2) indexes; SIFT embeddings | [7.7/AGENTS.md](7.7/AGENTS.md) |
| [`8.0/`](8.0/AGENTS.md) | 8.0 | Magma | Adds `bucket11` for BHive indexes; encryption at rest + DEK rotation; CCV; conflict-logged XDCR | [8.0/AGENTS.md](8.0/AGENTS.md) |
| [`8.1/`](8.1/AGENTS.md) | 8.1 | Magma | Adds `bucket11` BHive + CCV in scope; per-bucket history seconds tuned; scope/collection counts scaled higher | [8.1/AGENTS.md](8.1/AGENTS.md) |

---

## Feature Evolution Across Versions

| Feature | cheshirecat | neo | 7.2 | 7.6 | 7.7 | 8.0 | 8.1 |
|---------|:-----------:|:---:|:---:|:---:|:---:|:---:|:---:|
| Magma storage | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| History retention | — | — | — | ✓ | ✓ | ✓ | ✓ |
| Bucket rank | — | — | — | ✓ | ✓ | ✓ | ✓ |
| GSI shard affinity | — | — | — | ✓ | ✓ | ✓ | ✓ |
| `bucket10` (vector/composite) | — | — | — | — | ✓ | ✓ | ✓ |
| `bucket11` (BHive) | — | — | — | — | — | ✓ | ✓ |
| Encryption at rest | — | — | — | — | — | ✓ | ✓ |
| DEK rotation | — | — | — | — | — | ✓ | ✓ |
| Cross-cluster versioning | — | — | — | — | — | ✓ | ✓ |
| Conflict-logged XDCR | — | — | — | — | — | ✓ | ✓ |
| Audit logging | — | ✓ | — | — | — | — | — |
| Backup service | optional | optional | ✓ | ✓ | ✓ | ✓ | ✓ |
| Sync Gateway | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

---

## Loose Files (Pre-Series)

The `.yml` files directly in `tests/integration/` are historical tests that pre-date the sub-folder series. They follow a similar structure but are not organized by release version. Key ones:

| File Pattern | Notes |
|-------------|-------|
| `test_allFeatures*.yml` | Full-service tests at various stages (vulcan, alice, madhatter eras) |
| `test_XattrsAllFeatures*.yml` | Xattrs-focused integration |
| `test_dcpRollback.yml` | DCP rollback scenario |
| `test_extendedLongevity.yml` | Extended longevity run |
| `scope_8x4*.yml` | 8-node × 4-service distribution scopes |
| `scope_XattrsReplicaIndex*.yml` | Xattrs + replica index scopes |
| `scope_Xattrs_*.yml` | Xattrs scopes by era (Vulcan, Alice, Madhatter) |
| `scope_*Node*.yml` | Cluster size variants |

---

## Common Topology

All tests in the sub-folder series share the same two-cluster topology:

```
Local cluster  ──XDCR──►  Remote cluster
(primary: all services)    (XDCR target: data-only)
31 nodes (29 active)       2–8 nodes (all active)
2 held as rebalance-in     varies by version
targets
```

XDCR replication covers 4 bucket pairs. Sync Gateway attaches to `bucket7` (or equivalent) on the local cluster.

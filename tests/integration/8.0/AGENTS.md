# Integration Test — 8.0 (Magma)

Multi-service integration test for Couchbase 8.0 using Magma storage. Extends 7.7 by introducing a twelfth bucket (`bucket11`) for BHive vector indexes, adding encryption at rest with DEK rotation across all major buckets, enabling client certificate handling, and adding cross-cluster versioning (CCV). Vector search coverage expands: `bucket10` uses composite L2 indexes, `bucket11` uses BHive indexes.

## What Changed Since 7.7

| Area | 7.7 | 8.0 |
|------|-----|-----|
| Local buckets | 11 | **12** (`bucket11` added for BHive indexes) |
| `bucket11` | — | **Magma, 5% RAM**; SIFT 128-dim vectors; BHive vector indexes (4 deferred + 13 scalar) |
| Encryption at rest | — | **✓ cluster-level** (`enable_encryption_at_rest: true`, `enable_client_certificate_handling: true`) |
| DEK rotation | — | **✓** `dekRotateEvery: 50`, `dekLifetime: 100` — cluster and per-bucket |
| Per-bucket encryption | — | **✓** `enableEncryptionAtRest: true` on buckets 0–10 (bucket11 excluded) |
| Cross-cluster versioning | — | **✓** enabled on local buckets 0, 4, 8, 9 + all 4 remote buckets |
| XDCR conflict logging | — | **✓** all 4 replications use `--conflict-logging 1` with per-replication collection targets |
| XDCR CLI | `couchbase-cli:7.6` | **`couchbase-cli:8.0`** for CCV and XDCR commands |
| CCV sleep | — | **+60 s** after CCV enable (allows conflict-logging collections to initialize) |
| Vector query workload | — | **✓ `query_manager:dev`** on buckets 10 (L2) and 11 (BHive) |
| Catapult initial load | `scale × 500` | **`scale × 2000`** per bucket (4× increase) |
| Pillowfight `default` | 512 B | **128 B** (tighter KV traffic on primary bucket) |
| Pillowfight batches | `scale × 100` | **`scale × 200`** |
| Pillowfight rate-limit | `scale × 500` | **`scale × 1000`** |

**Summary:** 8.0 is the security and XDCR-versioning release. Encryption at rest with DEK rotation, cross-cluster versioning, conflict-logged XDCR, and BHive vector indexes on a new twelfth bucket are the headline additions. KV load is also significantly scaled up (4× catapult, 2× pillow rate-limit).

---

## Files

| File | Purpose |
|------|---------|
| `scope_8.0_magma.yml` | Infrastructure — 31 local + 6 remote nodes, 12 local buckets, encryption at rest |
| `test_8.0.yml` | Test workflow |

---

## Scope: `scope_8.0_magma.yml`

### Clusters

| Cluster | Nodes | Init nodes | Notes |
|---------|-------|-----------|-------|
| `local` | 31 | 29 | 2 held out; `enable_encryption_at_rest: true`, `enable_client_certificate_handling: true`, DEK rotate every 50 / lifetime 100 |
| `remote` | 6 | 6 | XDCR target, data-only |

### Local Cluster — Service Distribution

| Service | Count |
|---------|-------|
| Data (KV) | 16 |
| Index (GSI) | 6 |
| Query (N1QL) | 2 |
| FTS | 3 |
| Eventing | 3 |
| Analytics | 3 |
| Backup | 1 |

Memory: 50% data RAM, 80% index RAM, 80% FTS RAM, 90% eventing/analytics RAM.

### Local Buckets (12 total)

| Idx | Name | RAM | Encryption | History Bytes | History Secs | Rank | Notes |
|-----|------|-----|-----------|--------------|-------------|------|-------|
| 0 | `default` | 35% | ✓ | 2 GB | 3600 | 3 | DDocs `scale`, CCV enabled |
| 1 | `WAREHOUSE` | 15% | ✓ | 268 GB | 3600 | 3 | CCV enabled |
| 2 | `NEW_ORDER` | 5% | ✓ | 2 GB | 3600 | 2 | TTL 10800 s |
| 3 | `ITEM` | 5% | ✓ | 50 GB | 7200 | 2 | DDocs `all` |
| 4 | `bucket4` | 5% | ✓ | 2 GB | 14440 | 1 | CCV enabled; XDCR source |
| 5 | `bucket5` | 5% | ✓ | 2 GB | 86400 | 1 | Backup target; GSI + FTS |
| 6 | `bucket6` | 4% | ✓ | 2 GB | 86400 | 1 | GSI + FTS |
| 7 | `bucket7` | 4% | ✓ | 2 GB | 86400 | 1 | SGW source; GSI + FTS |
| 8 | `bucket8` | 4% | ✓ | 2 GB | 86400 | 1 | CCV enabled; XDCR source; Collections CRUD |
| 9 | `bucket9` | 4% | ✓ | 2 GB | 86400 | — | CCV enabled; XDCR source; Collections CRUD |
| 10 | `bucket10` | 5% | ✓ | 2 GB | 86400 | — | Composite + L2 vector indexes (SIFT 128-dim) |
| 11 | `bucket11` | 5% | — | 2 GB | 86400 | — | **New in 8.0** — BHive vector indexes; no encryption |

All buckets: Magma, fullEviction, `enablehistoryretentionbydefault: 1`. DEK lifetime 100, rotate every 50 (except `bucket11` which has no encryption config).

### Remote Buckets (4 total)

| Idx | Name | Encryption | Notes |
|-----|------|-----------|-------|
| 0 | `remote` | ✓ | 80% RAM |
| 1 | `bucket4` | — | CCV enabled |
| 2 | `bucket8` | — | CCV enabled |
| 3 | `bucket9` | — | CCV enabled |

---

## Test: `test_8.0.yml`

### Key Differences vs 7.7

| Feature | 7.7 | 8.0 |
|---------|-----|-----|
| Encryption at rest | — | ✓ (cluster + most buckets) |
| Client certificate handling | — | ✓ |
| DEK rotation | — | ✓ (every 50, lifetime 100) |
| Local buckets | 11 | **12** (`bucket11` added) |
| `bucket11` | — | BHive indexes + SIFT vectors |
| Cross-cluster versioning | — | ✓ (local 0,4,8,9 + remote 0–3) |
| XDCR conflict logging | — | ✓ (4 replications with logging) |
| XDCR CLI | `couchbase-cli:7.6` | `couchbase-cli:8.0` (for CCV commands) |
| N1QL query manager | — | `sequoiatools/query_manager:dev` on buckets 10, 11 |

### Phase 1 — Cluster Configuration (one-time)

Same base steps as 7.6/7.7 (tombstone purge, shard affinity, N2N encryption, IPv4 only, autofailover, Plasma Bloom Filter, OSO, redistribution, FTS options). Backup plan created for `bucket5`.

### Phase 2 — Scope & Collection Setup + CCV + XDCR

Scopes/collections on local buckets 4–9 and remote buckets 4, 8, 9. Sleep 300 s.

**Cross-Cluster Versioning** enabled on:
- Local: `default` (idx 0), `bucket4` (idx 4), `bucket8` (idx 8), `bucket9` (idx 9)
- Remote: all 4 buckets (idx 0–3)

Sleep 60 s for conflict-logging collection initialization.

**XDCR replications** (4 total, compression + conflict logging):

| Source | Target | Conflict Log Collection |
|--------|--------|------------------------|
| `default` | remote bucket 0 | `ITEM.event_0.coll0` |
| `bucket4` | remote bucket 1 | `ITEM.event_0.coll1` |
| `bucket8` | remote bucket 2 | `ITEM.event_0.coll2` |
| `bucket9` | remote bucket 3 | `ITEM.event_0.coll3` |

### Phase 3 — Data Loading

- catapult initial creates: buckets 4–9
- magmaloader: 100k Hotel docs to `bucket10` and `bucket11`
- SIFT 128-dim vectors: `bucket10` and `bucket11`
- `bucket10`: composite + L2 vector indexes (deferred, `scale × 1` + 13 scalar indexes)
- `bucket11`: BHive indexes (deferred, `scale × 1` + 13 scalar indexes)
- Background: transactions, collections CRUD (buckets 8/9), pillowfight all 10 data buckets, catapult incremental (buckets 4–7), gideon eventing source

### Phase 4 — Service Setup

GSI (buckets 4–7, 10, 11), FTS (buckets 4–7), eventing deploy, analytics setup, N1QL UDFs (buckets 4–7), N1QL query workloads, vector query workloads (`query_manager:dev` on buckets 10/11), FTS queries, Sync Gateway.

### Phases 5–6 — Topology & Validation

Same pattern as 7.7 with the addition of `query_manager` container cleanup. XDCR item count validation covers the 4 conflict-logged replications.

### Cross-Referenced Tests

| File | Sections |
|------|---------|
| `tests/eventing/CC/test_eventing_rebalance_integration.yml` | `create_and_deploy`, `topology_change`, `pause`, `resume`, `undeploy_delete` |
| `tests/analytics/cheshirecat/test_analytics_integration_scale3.yml` | `analytics_setup`, `analytics_query`, `analytics_topology_change`, `analytics_teardown` |
| `tests/2i/cheshirecat/test_idx_cc_integration.yml` | `change_indexer_topologies` |

### Running

```bash
./sequoia -provider file:hosts.json -skip_setup \
  -scope tests/integration/8.0/scope_8.0_magma.yml \
  -test  tests/integration/8.0/test_8.0.yml
```

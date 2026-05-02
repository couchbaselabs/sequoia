# Integration Test — 7.7 (Magma)

Multi-service integration test for Couchbase 7.7 using Magma storage. Extends 7.6 by introducing an eleventh local bucket (`bucket10`) dedicated to GSI composite and FTS vector index workloads, and adjusts collection densities for buckets 6–9 (reduced RAM allocation, increased scope/collection counts in the test).

## What Changed Since 7.6

| Area | 7.6 | 7.7 |
|------|-----|-----|
| Local buckets | 10 | **11** (`bucket10` added) |
| `bucket10` | — | **Magma, 4% RAM**; magmaloader + SIFT 128-dim vectors; composite + L2 vector indexes |
| Buckets 6–9 RAM | 5% each | **4% each** (freed RAM for bucket10) |
| Alternate scope | `scope_7.6_magma_cluster2.yml` | **Dropped** — single scope only |
| CLI image | `couchbase-cli:7.6` | `couchbase-cli:7.6` (unchanged) |
| History retention | ✓ | ✓ (unchanged; `default` bytes 2 GB/3600 s vs 7.6's 2 GB/3600 s) |
| XDCR | Compression only | Unchanged |
| Vector search | — | **✓** composite + L2 vector indexes on bucket10 via `indexmanager` |
| SIFT embeddings | — | **✓** 100k 128-dim vectors loaded via `siftloader` |

**Summary:** 7.7 introduces vector search coverage. A dedicated eleventh bucket (`bucket10`) receives Hotel document embeddings from the SIFT dataset and gets composite + L2 distance vector indexes alongside scalar secondary indexes. RAM is rebalanced from buckets 6–9 to accommodate. The 25-node alternate scope from 7.6 is not carried forward.

---

## Files

| File | Purpose |
|------|---------|
| `scope_7.7_magma.yml` | Infrastructure — 31 local + 6 remote nodes, 11 local buckets |
| `test_7.7.yml` | Test workflow |

---

## Scope: `scope_7.7_magma.yml`

### Clusters

| Cluster | Nodes | Init nodes | Notes |
|---------|-------|-----------|-------|
| `local` | 31 | 29 | 2 held out for rebalance ops |
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

Memory: 50% data RAM, 80% index RAM, 80% FTS RAM, 90% eventing/analytics RAM. No encryption at rest.

### Local Buckets (11 total)

| Idx | Name | RAM | History Bytes | History Secs | Rank | Notes |
|-----|------|-----|--------------|-------------|------|-------|
| 0 | `default` | 35% | 128 GB | 86400 | 3 | DDocs `scale`, compression active; XDCR source |
| 1 | `WAREHOUSE` | 15% | 268 GB | 43200 | 3 | |
| 2 | `NEW_ORDER` | 5% | 2 GB | 3600 | 2 | TTL 10800 s |
| 3 | `ITEM` | 5% | 50 GB | 7200 | 2 | DDocs `all` |
| 4 | `bucket4` | 5% | 2 GB | 14440 | 1 | XDCR source |
| 5 | `bucket5` | 5% | 2 GB | 86400 | 1 | Backup target; GSI + FTS |
| 6 | `bucket6` | 4% | 2 GB | 86400 | 1 | GSI + FTS (reduced from 5%) |
| 7 | `bucket7` | 4% | 2 GB | 86400 | 1 | SGW source; GSI + FTS (reduced from 5%) |
| 8 | `bucket8` | 4% | 2 GB | 86400 | 1 | XDCR source; Collections CRUD (reduced from 5%) |
| 9 | `bucket9` | 4% | 2 GB | 86400 | — | XDCR source; Collections CRUD (reduced from 5%) |
| 10 | `bucket10` | 4% | 2 GB | 86400 | — | **New in 7.7** — magmaloader + SIFT vector data; composite/vector indexes |

All buckets: Magma, fullEviction, `enablehistoryretentionbydefault: 1`.

### Remote Buckets (4 total — same as 7.2/7.6)

| Idx | Name |
|-----|------|
| 0 | `remote` (80% RAM) |
| 1 | `bucket4` |
| 2 | `bucket8` |
| 3 | `bucket9` |

---

## Test: `test_7.7.yml`

### Key Differences vs 7.6

| Feature | 7.6 | 7.7 |
|---------|-----|-----|
| Local buckets | 10 | **11** (`bucket10` added) |
| `bucket10` data | — | 100k Hotel docs via magmaloader + SIFT 128-dim vectors |
| `bucket10` indexes | — | Composite + vector indexes (L2) |
| Buckets 6–9 RAM | 5% | **4%** |
| Collection scale on `bucket5` | `scale × 2` scopes / `scale × 10` coll | `scale × 2` / `scale × 10` (same) |
| CLI image | `couchbase-cli:7.6` | `couchbase-cli:7.6` (unchanged) |

### Phase 1 — Cluster Configuration (one-time)

Same as 7.6: tombstone purge, shard affinity, N2N encryption, IPv4 only, autofailover, Plasma Bloom Filter, OSO mode, index redistribution, FTS options, backup plan.

### Phase 2 — Scope & Collection + XDCR Setup

Same 6-bucket scope/collection pattern on local and 3 remote buckets. XDCR replications without conflict logging (same as 7.6).

### Phase 3 — Data Loading

- catapult initial creates on buckets 4–9
- magmaloader: 100k Hotel docs to `bucket10`
- SIFT vector embeddings (128-dim, L2) on `bucket10`
- Composite + vector index creation on `bucket10` (deferred, then built)
- Background workloads: transactions, collections CRUD, pillowfight on all 10 data buckets, catapult incremental on buckets 4–7, gideon eventing source

### Phase 4 — Index & Service Setup

GSI create + build (buckets 4–7 + 10), FTS create (buckets 4–7), eventing deploy, analytics setup, N1QL UDFs (buckets 4–7), N1QL queries, FTS queries, Sync Gateway.

### Phases 5–6 — Topology Changes & Validation

Same sequence as 7.2/7.6: rebalance out/swap → eventing/analytics topology changes → view attacks → XDCR filtering → failover scenarios → FTS failover/rebalance ops → undeploy/teardown → item count validation (XDCR, GSI, FTS) → index drops.

### Cross-Referenced Tests

| File | Sections |
|------|---------|
| `tests/eventing/CC/test_eventing_rebalance_integration.yml` | `create_and_deploy`, `topology_change`, `pause`, `resume`, `undeploy_delete` |
| `tests/analytics/cheshirecat/test_analytics_integration_scale3.yml` | `analytics_setup`, `analytics_query`, `analytics_topology_change`, `analytics_teardown` |
| `tests/2i/cheshirecat/test_idx_cc_integration.yml` | `change_indexer_topologies` |

### Running

```bash
./sequoia -provider file:hosts.json -skip_setup \
  -scope tests/integration/7.7/scope_7.7_magma.yml \
  -test  tests/integration/7.7/test_7.7.yml
```

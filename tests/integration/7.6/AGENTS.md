# Integration Test — 7.6 (Magma)

Multi-service integration test for Couchbase 7.6 using Magma storage. Builds on the 7.2 baseline by adding shard affinity (file-based rebalance for GSI), bucket history retention, and bucket priority ranking. Two scope variants exist: a full 31-node cluster and a smaller 25-node alternate cluster for lighter environments.

## What Changed Since 7.2

| Area | 7.2 | 7.6 |
|------|-----|-----|
| CLI image | `couchbase-cli:7.2` | **`couchbase-cli:7.6`** |
| GSI shard affinity | — | **✓ `indexer.settings.enable_shard_affinity: true`** |
| History retention | — | **✓** all buckets (`historyretentionbytes` + `historyretentionseconds` + `enablehistoryretentionbydefault`) |
| Bucket rank | — | **✓** (rank 1–3 on all buckets) |
| Alternate scope | — | **✓ `scope_7.6_magma_cluster2.yml`** (25/23 local, 3 remote) |
| Remote cluster | 6 nodes | 6 nodes (unchanged) |
| Catapult, pillowfight | `scale × 500`, 512 B | Unchanged |
| XDCR | Compression only | Unchanged (conflict logging not yet added) |

**Summary:** 7.6 is the history-retention and shard-affinity release. The shard affinity setting enables file-based GSI rebalance, significantly improving rebalance reliability for large index sets. History retention gives buckets time-travel CDC capability. A lighter 25-node alternate scope is introduced to support environments with fewer servers.

---

## Files

| File | Purpose |
|------|---------|
| `scope_7.6_magma.yml` | Full infrastructure — 31 local + 6 remote nodes |
| `scope_7.6_magma_cluster2.yml` | Smaller alternate — 25 local + 3 remote nodes |
| `test_7.6.yml` | Test workflow (used with either scope) |

---

## Scope: `scope_7.6_magma.yml` (Primary)

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

### Local Buckets (10 total)

| Idx | Name | RAM | History Bytes | History Secs | Rank | Notes |
|-----|------|-----|--------------|-------------|------|-------|
| 0 | `default` | 35% | 2 GB | 3600 | 3 | DDocs `scale`, compression active; XDCR source |
| 1 | `WAREHOUSE` | 15% | 268 GB | 3600 | 3 | |
| 2 | `NEW_ORDER` | 5% | 2 GB | 3600 | 2 | TTL 10800 s |
| 3 | `ITEM` | 5% | 50 GB | 7200 | 2 | DDocs `all` |
| 4 | `bucket4` | 5% | 2 GB | 14440 | 1 | XDCR source |
| 5 | `bucket5` | 5% | 2 GB | 86400 | 1 | Backup target; GSI + FTS |
| 6 | `bucket6` | 5% | 2 GB | 86400 | 1 | GSI + FTS |
| 7 | `bucket7` | 5% | 2 GB | 86400 | 1 | SGW source; GSI + FTS |
| 8 | `bucket8` | 5% | 2 GB | 86400 | 1 | XDCR source; Collections CRUD |
| 9 | `bucket9` | 5% | 2 GB | 86400 | — | XDCR source; Collections CRUD |

All buckets: Magma, fullEviction, `enablehistoryretentionbydefault: 1`.

### Scope: `scope_7.6_magma_cluster2.yml` (Alternate — Smaller)

| Cluster | Nodes | Init nodes | Services |
|---------|-------|-----------|---------|
| `local` | 25 | 23 | index×4, query×2, backup×1, fts×2, eventing×2, analytics×3 |
| `remote` | 3 | 3 | data-only |

Same 10+4 bucket names and structure, different history byte limits (local `default`: 128 GB, `WAREHOUSE`: 268 GB). Smaller clusters for environments with fewer resources.

---

## Test: `test_7.6.yml`

### Key Differences vs 7.2

| Feature | 7.2 | 7.6 |
|---------|-----|-----|
| CLI image | `couchbase-cli:7.2` | `couchbase-cli:7.6` |
| Shard affinity (`enable_shard_affinity`) | — | ✓ (added) |
| History retention on buckets | — | ✓ |
| Bucket rank | — | ✓ |

### Phase 1 — Cluster Configuration (one-time)

| Step | Action |
|------|--------|
| 1 | Tombstone purge interval 0.25, compaction 30% |
| **2** | **Enable GSI shard affinity** (`indexer.settings.enable_shard_affinity`) ← new in 7.6 |
| 3 | Disable autofailover |
| 4 | Enable N2N encryption, set level `control`, set IPv4 only |
| 5 | Re-enable autofailover (120 s, 1 node) |
| 6 | Enable Plasma Bloom Filter |
| 7 | Enable GSI OSO mode |
| 8 | Enable GSI index redistribution |
| 9 | Set FTS `bleveMaxResultWindow` → 100000, `bleveMaxClauseCount` → 2500 |
| 10 | Create backup plan (24 h backup, 2-day merge) + repo for `bucket5` |

### Phases 2–6

Identical structure to 7.2: scope/collection setup (buckets 4–8/9, `scale × 2` scopes / `scale × 10` collections), XDCR (compression, no conflict logging), catapult initial + incremental loads, pillowfight on all 10 buckets, GSI/FTS/eventing/analytics/2i setup and topology changes, full teardown and validation.

The catapult loads remain at the 7.2 scale (`scale × 500` initial), and pillowfight settings are identical.

### Cross-Referenced Tests

| File | Sections |
|------|---------|
| `tests/eventing/CC/test_eventing_rebalance_integration.yml` | `create_and_deploy`, `topology_change`, `pause`, `resume`, `undeploy_delete` |
| `tests/analytics/cheshirecat/test_analytics_integration_scale3.yml` | `analytics_setup`, `analytics_query`, `analytics_topology_change`, `analytics_teardown` |
| `tests/2i/cheshirecat/test_idx_cc_integration.yml` | `change_indexer_topologies` |

### Running

```bash
# Full cluster
./sequoia -provider file:hosts.json -skip_setup \
  -scope tests/integration/7.6/scope_7.6_magma.yml \
  -test  tests/integration/7.6/test_7.6.yml

# Smaller cluster
./sequoia -provider file:hosts.json -skip_setup \
  -scope tests/integration/7.6/scope_7.6_magma_cluster2.yml \
  -test  tests/integration/7.6/test_7.6.yml
```

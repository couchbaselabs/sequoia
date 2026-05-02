# Integration Test — 7.2 (Magma)

Baseline multi-service integration test for Couchbase 7.2 using Magma storage. Covers KV, GSI, FTS, N1QL, Analytics, Eventing, XDCR, Views, Sync Gateway, and Backup across a two-cluster topology. This is the earliest version in the versioned integration test series; it lacks shard affinity, bucket history retention, bucket ranking, and encryption at rest — all added in later releases.

## What Changed Since Neo

> **Neo vs 7.2 relationship:** The scope files are structurally near-identical (same 31/29 local node count with full service set, same 10+4 Magma bucket layout, same bucket names). The differences are in test configuration and cluster tuning — 7.2 formalises the versioned test series with a pinned CLI, fixes an OSO bug workaround, and adjusts cluster sizing. The milestone decomposition pattern from Neo is **dropped** in favour of a single complete test file.

| Area | Neo | 7.2 |
|------|-----|-----|
| CLI image | `couchbase-cli` (unversioned) | **`couchbase-cli:7.2`** (pinned) |
| Audit logging | ✓ | **Removed** |
| GSI OSO mode | Commented out (MB-43725) | **Re-enabled** (bug resolved) |
| Plasma in-memory compression | Disabled | Still not present |
| GSI shard affinity | — | — (added in 7.6) |
| Tombstone purge interval | 0.04 | **0.25** (relaxed) |
| Remote cluster nodes | 8 (primary scope) | **6** |
| Local FTS nodes | 2 | **3** |
| Data RAM | 80% | **50%** |
| Index RAM | 50% | **80%** |
| Milestone decomposition | ✓ | **Dropped** — single test file |
| Catapult initial load | (similar scale) | `scale × 500` per bucket |
| Pillowfight per bucket | (similar) | `scale × 500` docs, 512 B, batch 100 |

**Summary:** 7.2 is a clean, versioned, production-ready codification of the Neo/Magma baseline. The main practical differences are the versioned CLI, OSO re-enablement, 3 FTS nodes, smaller remote cluster, and the removal of the milestone decomposition pattern. No new Couchbase features are introduced relative to Neo.

---

## Files

| File | Purpose |
|------|---------|
| `scope_7.2_magma.yml` | Infrastructure — two clusters, 10 local + 4 remote Magma buckets, users, views, sync gateway |
| `test_7.2.yml` | Test workflow — ordered actions from configuration through teardown and validation |

---

## Scope: `scope_7.2_magma.yml`

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

| Idx | Name | RAM | TTL | DDocs | Notes |
|-----|------|-----|-----|-------|-------|
| 0 | `default` | 35% | — | `scale` | compression: active; XDCR source → remote bucket 0 |
| 1 | `WAREHOUSE` | 15% | — | — | |
| 2 | `NEW_ORDER` | 5% | 10800 s | — | |
| 3 | `ITEM` | 5% | — | `all` | |
| 4 | `bucket4` | 5% | — | — | XDCR source → remote bucket 1 |
| 5 | `bucket5` | 5% | — | — | Backup plan target; GSI + FTS indexes |
| 6 | `bucket6` | 5% | — | — | GSI + FTS indexes |
| 7 | `bucket7` | 5% | — | — | Sync Gateway source; GSI + FTS indexes |
| 8 | `bucket8` | 5% | — | — | XDCR source → remote bucket 2; Collections CRUD |
| 9 | `bucket9` | 5% | — | — | XDCR source → remote bucket 3; Collections CRUD |

No history retention, no bucket rank, no encryption — all storage is Magma + fullEviction.

### Remote Buckets (4 total)

| Idx | Name | RAM |
|-----|------|-----|
| 0 | `remote` | 80% |
| 1 | `bucket4` | — |
| 2 | `bucket8` | — |
| 3 | `bucket9` | — |

### Key Differences vs Later Versions

- No `historyretentionbytes` / `historyretentionseconds` on any bucket
- No bucket `rank` field
- No `enable_encryption_at_rest` or `enableEncryptionAtRest`
- No shard affinity (`indexer.settings.enable_shard_affinity` not set)
- CLI image: `sequoiatools/couchbase-cli:7.2`
- Smaller catapult loads (`scale × 500` per bucket vs `scale × 2000` in 8.x)
- Smaller pillowfight rate: `scale × 500` docs, `scale × 100` batch, 512 B docs

---

## Test: `test_7.2.yml`

### Phase 1 — Cluster Configuration (one-time)

| Step | Action |
|------|--------|
| 1 | Set tombstone purge interval 0.25, DB/view compaction 30% |
| 2 | Disable autofailover |
| 3 | Enable node-to-node encryption |
| 4 | Set cluster encryption level to `control` |
| 5 | Set IP family to IPv4 only |
| 6 | Re-enable autofailover (120 s, 1 node) |
| 7 | Enable Plasma Bloom Filter |
| 8 | Enable GSI OSO mode |
| 9 | Enable GSI index redistribution on rebalance |
| 10 | Set FTS `bleveMaxResultWindow` → 100000 |
| 11 | Set FTS `bleveMaxClauseCount` → 2500 |
| 12 | Create backup plan `my_plan` (24 h backup, 2-day merge) + repo for `bucket5` |

> **Note:** No shard affinity step — added in 7.6.

### Phase 2 — Scope & Collection + XDCR Setup (one-time)

Scopes/collections created on local buckets 4–9 and remote buckets 4, 8, 9 (`scale × 2` scopes, `scale × 10` collections each, uniform). 300 s sleep for manifest sync. XDCR replications (compression only, no conflict logging) for `default→remote0`, `bucket4→remote1`, `bucket8→remote2`, `bucket9→remote3`.

### Phase 3 — Data Loading & Background Workloads

| Workload | Buckets | Doc count (scaled) | Notes |
|----------|---------|-------------------|-------|
| catapult (creates only) | bucket4–9 | `scale × 500` each | aliases: `catapult_bucketN_doc_ops1` |
| transactions | `default` | 1000 ops | alias: `txn` |
| collections CRUD | bucket8, bucket9 | max 10 scopes / 100 collections | aliases: `collection_crud1/2` |
| pillowfight (majority durability) | all 10 buckets | `scale × 500`, 512 B | continuous |
| catapult (incremental CRUD) | bucket4–7 | `scale × 3000`, expiry `scale × 3000` | aliases: `catapult_bucketN_doc_ops2` |
| gideon KV (eventing source) | `default` + `bucket1` scope `event_0/coll0` | `scale × 75` ops | TTL 3600 s |

### Phase 4 — Service Setup

GSI indexes on buckets 4–7, build deferred (batch size 2), wait for completion. FTS indexes on buckets 4–7 (300 s sleep between each). Eventing (`create_and_deploy`). Analytics (`analytics_setup`). N1QL UDFs (10 per scope, buckets 4–7). Sync Gateway (async). N1QL query workloads (`REQUEST_PLUS`) on buckets 4–7. FTS query + flex query workloads.

### Phase 5 — Topology Changes

Rebalance out → swap rebalance → eventing `topology_change` → analytics `topology_change` → view attacks → FTS child-field + nested-type indexes → XDCR advanced filtering → eventing pause → pillowfight_htp → 2i topology change → eventing resume → swap failover → XDCR pause/resume → swap hard failover → autofailover → FTS rebalance in/failover/addback/rebalance out → add 2 inactive nodes.

### Phase 6 — Teardown & Validation

Stop background containers → sleep 1200 s → XDCR item count check (buckets 4, 8, 9) → GSI item count check (`scale × 5` sample, buckets 4–7) → drop GSI indexes (buckets 4–9) → FTS item count check → drop FTS indexes (buckets 4–7) → drop UDFs → sleep.

### Cross-Referenced Tests

| File | Sections |
|------|---------|
| `tests/eventing/CC/test_eventing_rebalance_integration.yml` | `create_and_deploy`, `topology_change`, `pause`, `resume`, `undeploy_delete` |
| `tests/analytics/cheshirecat/test_analytics_integration_scale3.yml` | `analytics_setup`, `analytics_query`, `analytics_topology_change`, `analytics_teardown` |
| `tests/2i/cheshirecat/test_idx_cc_integration.yml` | `change_indexer_topologies` |

### Running

```bash
./sequoia -provider file:hosts.json -skip_setup \
  -scope tests/integration/7.2/scope_7.2_magma.yml \
  -test  tests/integration/7.2/test_7.2.yml
```

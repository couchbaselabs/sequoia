# Integration Test — 8.1 (Magma)

Comprehensive multi-service integration test for Couchbase 8.1 using Magma storage. Exercises KV, GSI, FTS, N1QL, Analytics, Eventing, XDCR, Views, Sync Gateway, and Backup across a two-cluster topology with topology-change scenarios throughout.

## What Changed Since 8.0

The scope files are structurally identical between 8.0 and 8.1 — the same 12 buckets, same service layout, same encryption/DEK settings. All changes are in the **test workflow**, primarily targeting collection scalability stress.

| Area | 8.0 | 8.1 |
|------|-----|-----|
| **Scope/collection density — bucket5** | `scale × 2` scopes / `scale × 10` coll | **`scale × 3000` scopes / `scale × 8000` coll** — extreme collection limit stress |
| Scope/collection — bucket6 | `scale × 2` / `scale × 10` | `scale × 10` / `scale × 500` |
| Scope/collection — bucket7 | `scale × 2` / `scale × 10` | `scale × 5` / `scale × 500` |
| Scope/collection — bucket8 | `scale × 1` / `scale × 10` | `scale × 10` / `scale × 500` |
| Scope/collection — bucket9 | `scale × 1` / `scale × 10` | `scale × 1` / `scale × 700` |
| Collections CRUD — bucket8 | `max_collections=100` | **`max_collections=500`** |
| Collections CRUD — bucket9 | `max_scopes=10`, `max_collections=100` | `max_scopes=5`, **`max_collections=700`** |
| Catapult initial — bucket5 | `scale × 2000` | **`scale × 2`** (reduced; collection density carries load) |
| Catapult initial — bucket6 | `scale × 2000` | **`scale × 40`** |
| Catapult initial — bucket7 | `scale × 2000` | **`scale × 40`** |
| Catapult initial — bucket8 | `scale × 2000` | **`scale × 40`** |
| Catapult initial — bucket9 | `scale × 2000` | **`scale × 35`** |
| Catapult incremental — bucket5 | `scale × 3000`, expiry `scale × 3000` | **`scale × 3`**, expiry `scale × 7200` |
| Catapult incremental — bucket6/7 | `scale × 3000`, expiry `scale × 3000` | **`scale × 40`**, expiry `scale × 7200` |
| Pillowfight — bucket5 | `scale × 2000` | **`scale × 500`** |
| Gideon eventing source TTL | (default) | Explicit `--ttl 3600` on `event_0/coll0` for both `default` and `bucket1` |

**Summary:** 8.1 is a collection-scalability stress release. The single largest change is `bucket5` expanding to `scale × 3000` scopes and `scale × 8000` collections — a deliberate boundary stress test for the collection manifest system. Per-bucket catapult loads are deliberately reduced on the high-collection buckets so total data volume stays reasonable. The scope file is unchanged from 8.0.

---

## Files

| File | Purpose |
|------|---------|
| `scope_8.1_magma.yml` | Infrastructure definition — two clusters, 12 local buckets, 4 remote buckets, users, views, sync gateway |
| `test_8.1.yml` | Test workflow — ordered actions from initial setup through teardown and validation |

---

## Scope: `scope_8.1_magma.yml`

### Clusters

| Cluster | Nodes | Notes |
|---------|-------|-------|
| `local` | 31 total, **29 initially joined** (2 held out for rebalance ops) | Primary cluster |
| `remote` | 6 total, all joined | XDCR target cluster |

### Local Cluster — Service Distribution

| Service | Count |
|---------|-------|
| Data (KV) | 16 (31 − 6 index − 2 query − 1 backup − 3 FTS − 3 eventing) |
| Index (GSI) | 6 |
| Query (N1QL) | 2 |
| FTS | 3 |
| Eventing | 3 |
| Analytics | 3 |
| Backup | 1 |

Memory allocation: 50% RAM for data, 80% for index, 80% for FTS, 90% for eventing/analytics.  
Additional settings: `enable_encryption_at_rest: true`, `enable_client_certificate_handling: true`, DEK rotation every 50 ops / lifetime 100.

### Remote Cluster — Service Distribution

All 6 nodes are data-only. REST credentials match the local cluster (`Administrator`/`password`).

### Local Buckets (12 total)

| Index | Name | RAM | Storage | TTL | History Bytes | History Secs | Notes |
|-------|------|-----|---------|-----|---------------|--------------|-------|
| 0 | `default` | 35% | magma | — | 2 GB | 3600 | rank 3, views DDocs (`scale`), CCV enabled |
| 1 | `WAREHOUSE` | 15% | magma | — | 268 GB | 3600 | rank 3, CCV enabled |
| 2 | `NEW_ORDER` | 5% | magma | 10800 s | 2 GB | 3600 | rank 2 |
| 3 | `ITEM` | 5% | magma | — | 50 GB | 7200 | rank 2, views DDocs (`all`) |
| 4 | `bucket4` | 5% | magma | — | 2 GB | 14440 | CCV enabled; XDCR source → remote bucket 1 |
| 5 | `bucket5` | 5% | magma | — | 2 GB | 86400 | Backup plan target; many GSI + FTS indexes |
| 6 | `bucket6` | 4% | magma | — | 2 GB | 86400 | GSI + FTS indexes |
| 7 | `bucket7` | 4% | magma | — | 2 GB | 86400 | Sync Gateway source; GSI + FTS indexes |
| 8 | `bucket8` | 4% | magma | — | 2 GB | 86400 | CCV enabled; XDCR source → remote bucket 2; Collections CRUD |
| 9 | `bucket9` | 4% | magma | — | 2 GB | 86400 | CCV enabled; XDCR source → remote bucket 3; Collections CRUD |
| 10 | `bucket10` | 5% | magma | — | 2 GB | 86400 | Composite + vector (L2) indexes; SIFT embeddings |
| 11 | `bucket11` | 5% | magma | — | 2 GB | 86400 | BHive + scalar indexes; SIFT embeddings |

All local buckets use `fullEviction` and encryption at rest (except `bucket11` which has no encryption configured).

### Remote Buckets (4 total)

| Index | Name | RAM | Notes |
|-------|------|-----|-------|
| 0 | `remote` | 80% | General remote bucket |
| 1 | `bucket4` | — | XDCR target for local `bucket4` |
| 2 | `bucket8` | — | XDCR target for local `bucket8` |
| 3 | `bucket9` | — | XDCR target for local `bucket9` |

### Users

11 users defined (all `admin` role, `local` auth domain):  
`default`, `WAREHOUSE`, `NEW_ORDER`, `ITEM`, `bucket4`–`bucket9`, `remote`

### Views (DDocs)

DDoc `scale` (on `default`, `WAREHOUSE`, `NEW_ORDER`):

| View | Map Logic |
|------|-----------|
| `stats` | Emit (meta.id, ops_sec) where rating in [500, 520] |
| `padd` | Emit (meta.id, padding) where rating < 200 |
| `array` | Emit (active_hosts, null) where rating in [200, 300] |

DDoc `all` (on `ITEM`):

| View | Map Logic |
|------|-----------|
| `all_ids` | Emit (meta.id, null) — all documents |

### Sync Gateway

One SGW node (`sg`) attached to the `local` cluster, serving `bucket7` via user `bucket7`.

---

## Test: `test_8.1.yml`

The test is structured into sequential phases. Actions marked `requires: "{{eq true .DoOnce }}"` only execute on the first loop iteration.

### Templates Included

```
tests/templates/rebalance.yml
tests/templates/vegeta.yml
tests/templates/kv.yml
tests/templates/fts.yml
tests/templates/n1ql.yml
tests/templates/multinode_failure.yml
tests/templates/collections.yml
```

### Phase 1 — Cluster Configuration (one-time)

| Step | Action | Tool/Image |
|------|--------|-----------|
| 1 | Set tombstone purge interval 0.25, DB/view compaction 30% | `couchbase-cli:7.6 setting-compaction` |
| 2 | Enable shard affinity for GSI (`indexer.settings.enable_shard_affinity`) | `set_gsi_config` template |
| 3 | Disable autofailover | `disable_autofailover` template |
| 4 | Enable node-to-node encryption | `couchbase-cli:7.6 node-to-node-encryption --enable` |
| 5 | Set cluster encryption level to `control` | `couchbase-cli:7.6 setting-security` |
| 6 | Set IP family to IPv4 only | `couchbase-cli:7.6 ip-family --ipv4only` |
| 7 | Re-enable autofailover (120 s timeout, 1 node) | `enable_autofailover` template |
| 8 | Enable Plasma Bloom Filter (`indexer.plasma.backIndex.enablePageBloomFilter`) | `set_gsi_config` template |
| 9 | Enable GSI OSO mode (`indexer.build.enableOSO`) | `set_gsi_config` template |
| 10 | Enable GSI index redistribution on rebalance | `set_gsi_config` template |
| 11 | Set FTS `bleveMaxResultWindow` → 100000 | `set_fts_manager_options` template |
| 12 | Set FTS `bleveMaxClauseCount` → 2500 | `set_fts_manager_options` template |

### Phase 2 — Backup Plan Setup (one-time)

| Step | Action |
|------|--------|
| 13 | Create backup plan `my_plan`: full backup every 24 h, merge every 2 days at noon; covers data, GSI, views, FTS, eventing, analytics, query |
| 14 | Create repository `my_repo` under `/data/archive` targeting `bucket5` |

### Phase 3 — Scope & Collection Setup (one-time)

Scopes and collections are created with the `create-multi-scopes-collections` template:

| Cluster | Bucket | Scopes (scaled) | Collections (scaled) | Pattern |
|---------|--------|-----------------|----------------------|---------|
| local | bucket4 (idx 4) | `scale × 2` | `scale × 10` | uniform |
| local | bucket5 (idx 5) | `scale × 3000` | `scale × 8000` | uniform |
| local | bucket6 (idx 6) | `scale × 10` | `scale × 500` | uniform |
| local | bucket7 (idx 7) | `scale × 5` | `scale × 500` | uniform |
| local | bucket8 (idx 8) | `scale × 10` | `scale × 500` | uniform |
| local | bucket9 (idx 9) | `scale × 1` | `scale × 700` | uniform |
| remote | bucket4 (idx 4) | `scale × 2` | `scale × 10` | uniform |
| remote | bucket8 (idx 8) | `scale × 2` | `scale × 10` | uniform |
| remote | bucket9 (idx 9) | `scale × 2` | `scale × 10` | uniform |

A 300-second sleep follows to allow collection manifests to sync across clusters.

### Phase 4 — Cross-Cluster Versioning & XDCR Setup (one-time)

**Enable CCV** on local buckets: `default` (idx 0), `bucket4` (idx 4), `bucket8` (idx 8), `bucket9` (idx 9).  
**Enable CCV** on remote buckets: all 4 (idx 0–3).  
A 60-second sleep follows to allow conflict-logging collections to initialize.

**XDCR Replications** (all with compression and conflict logging enabled):

| Source (local) | Target (remote) | Conflict Log Collection |
|----------------|-----------------|------------------------|
| `default` (idx 0) | remote bucket 0 | `ITEM.event_0.coll0` |
| `bucket4` (idx 4) | remote bucket 1 | `ITEM.event_0.coll1` |
| `bucket8` (idx 8) | remote bucket 2 | `ITEM.event_0.coll2` |
| `bucket9` (idx 9) | remote bucket 3 | `ITEM.event_0.coll3` |

### Phase 5 — Initial Data Loading

| Alias | Tool | Bucket | Doc Count (scaled) | Type |
|-------|------|--------|--------------------|------|
| `catapult_bucket4_doc_ops1` | catapult | bucket4 | `scale × 2000` | Hotel, create-only |
| `catapult_bucket5_doc_ops1` | catapult | bucket5 | `scale × 2` | Hotel, create-only |
| `catapult_bucket6_doc_ops1` | catapult | bucket6 | `scale × 40` | Hotel, create-only |
| `catapult_bucket7_doc_ops1` | catapult | bucket7 | `scale × 40` | Hotel, create-only |
| `catapult_bucket8_doc_ops1` | catapult | bucket8 | `scale × 40` | Hotel, create-only |
| `catapult_bucket9_doc_ops1` | catapult | bucket9 | `scale × 35` | Hotel, create-only |
| — | magmaloader | bucket10 | 100,000 | Hotel, `--all_coll true` |
| — | magmaloader | bucket11 | 100,000 | Hotel, `--all_coll true` |
| — | siftloader | bucket10 | 100,000 | SIFT vectors (128-dim, L2) |
| — | siftloader | bucket11 | 100,000 | SIFT vectors (128-dim, L2) |

### Phase 6 — Index Creation

**GSI Composite + Vector Indexes on bucket10:**
- 6 composite/vector indexes (deferred, max replicas 1, 128-dim L2, skip default collection: false)
- 13 scalar secondary indexes

**GSI BHive + Secondary Indexes on bucket11:**
- 4 BHive indexes (deferred, max replicas 1, 128-dim L2)
- 13 scalar secondary indexes

Both sets are built in parallel after creation. Wait for index build to complete using `wait_for_idx_build_complete`.

### Phase 7 — Background Workloads (async, long-running)

| Alias | Workload | Buckets |
|-------|---------|---------|
| `txn` | Transactions (1000 ops) | `default` |
| `collection_crud1` | Collections CRUD (120s interval, max 10 scopes, 500 collections) | bucket8 |
| `collection_crud2` | Collections CRUD (120s interval, max 5 scopes, 700 collections) | bucket9 |
| — | Pillowfight with majority durability (continuous) | All 10 buckets (idx 0–9) |
| — | gideon KV with expiry (TTL 3600 s) to eventing source | `default` scope `event_0/coll0`, bucket1 same |

Pillowfight settings per bucket:

| Bucket idx | Doc size | Doc count (scaled) | Batch (scaled) |
|------------|----------|--------------------|----------------|
| 0 | 128 B | 1000 | 200 |
| 1–3 | 256 B | 2000 | 200 |
| 4–9 | 512 B | 2000 (500 for idx 5) | 200 |

After starting workloads: sleep 600 s.

### Phase 8 — Topology Operations (ordered sequence)

| Step | Operation | Wait |
|------|-----------|------|
| Rebalance out | `ActiveDataNode 1` removed | yes |
| Sleep 600 s | — | yes |
| Eventing setup | `create_and_deploy` section from `tests/eventing/CC/test_eventing_rebalance_integration.yml` | — |
| Analytics setup | `analytics_setup` section from `tests/analytics/cheshirecat/test_analytics_integration_scale3.yml` | — |
| N1QL UDFs | Create 10 UDFs per scope on buckets 4–7 | yes |
| GSI indexes | Create indexes on buckets 5–7 (`scale × 1` per bucket) | yes |
| Deferred index build | Build on buckets 5–7, 10, 11 | yes |
| Wait for index build | `wait_for_idx_build_complete` on `ActiveIndexNode 0` | yes |
| FTS indexes | Create on buckets 4–7 (various partition maps), 300 s sleep between each | yes |
| Sync Gateway | SGW test via `sequoiatools/sgw` (async) | no |
| Incremental catapult | Buckets 4–7: CRUD with expiry, lazy load every 300 s | async |
| N1QL query workloads | QueryApp on buckets 4–7 (NOT_BOUNDED and REQUEST_PLUS) | async |
| Vector query workloads | query_manager on bucket10 (N1QL + vectors) and bucket11 (BHive) | async |
| FTS query workloads | Run queries and flex queries on buckets 4, 5 | async |
| Sleep 600 s | — | yes |
| Swap rebalance | `InActiveNode` in, `ActiveDataNode 2` out | yes |
| Sleep 600 s | — | yes |
| Analytics queries | `analytics_query` section | — |
| N1QL HTTP attack | `attack_query` on N1QL node 1 (delete from default, `scale × 10` limit) | — |
| gideon KV | Multi-workload on `default` bucket (create/get/delete/expire) | async/duration |
| Eventing topology change | `topology_change` section (rebalance in/out/swap eventing nodes) | — |
| Sleep 600 s | — | yes |
| Analytics topology change | `analytics_topology_change` section | — |
| Sleep 600 s | — | yes |
| View HTTP attacks | `attack_view` on `stats`, `array`, `padd` views across 3 data nodes | — |
| FTS child field index | `good_state` index on `default` bucket (scorch) | yes |
| FTS nested type mapping | `social` index on `default` bucket | — |
| XDCR replication ID | Capture via curl → alias `ReplId` | yes |
| XDCR advanced filtering | Apply `filterExpression`, `filterExpiration`, `filterBypassExpiry`, `filterDeletion` rules | yes |
| Pause eventing | `pause` section | — |
| pillowfight_htp | 1 M doc load | yes |
| 2i topology change | `change_indexer_topologies` section from `tests/2i/cheshirecat/test_idx_cc_integration.yml` | — |
| Sleep 600 s | — | yes |
| Resume eventing | `resume` section | — |
| pillowfight_htp | Quick update batch | yes |
| Swap failover | Add `InActiveNode`, hard failover `ActiveDataNode 1`, rebalance | yes |
| Sleep 600 s | — | yes |
| XDCR pause/resume | Pause `default` and `bucket8` replications, sleep 300 s, resume both | yes |
| gideon KV | New docs on `default` bucket (1800 s duration) | async |
| pillowfight_htp | Update batch | yes |
| Swap hard failover | Add node, failover `ActiveDataNode 2`, hard failover `ActiveDataNode 3`, rebalance | yes |
| Sleep 600 s | — | yes |
| Autofailover 1 node | `autofailover1Node` on `ActiveDataNode 1` | yes |
| Sleep 600 s | — | yes |
| pillowfight_htp | — | yes |
| Rebalance in FTS node | `InActiveNode` with `fts` service | yes |
| Sleep 900 s | — | yes |
| FTS failover + addback | Hard failover `NthFTSNode 1`, readd, full recovery, rebalance | yes |
| Sleep 900 s | — | yes |
| FTS failover + rebalance out | Hard failover `NthFTSNode 1`, rebalance | yes |
| Sleep 900 s | — | yes |
| Add 2 inactive nodes | `NthInActiveNode 0` and `NthInActiveNode 1`, rebalance | yes |
| Sleep 600 s | — | yes |

### Phase 9 — Teardown & Validation

| Step | Action | Tool |
|------|--------|------|
| Undeploy eventing | `undeploy_delete` section | eventing test |
| Analytics teardown | `analytics_teardown` section | analytics test |
| Stop background containers | rm: `collection_crud1`, `collection_crud2`, catapult ops 1 & 2 (all buckets), `txn` | client op |
| Sleep 1200 s | Allow final convergence | — |
| XDCR item count validation | Validate bucket4→remote-bucket1, bucket8→remote-bucket2, bucket9→remote-bucket3 | `xdcrmanager` |
| GSI item count check | buckets 4–7, sample size `scale × 10` | `indexmanager` |
| Drop GSI indexes | buckets 4–9 | `indexmanager` |
| FTS item count check | `default` bucket, verify timeout 2400 s | `ftsindexmanager` |
| Sleep 600 s | — | — |
| Drop FTS indexes | buckets 4–7, 600 s sleep between each | `ftsindexmanager` |
| Sleep 1200 s | Allow DDL background completion | — |
| Drop N1QL UDFs | bucket4 | `indexmanager` |
| Sleep 600 s | — | — |

---

## Cross-Referenced Tests

The following external test files are invoked by section:

| File | Sections Used |
|------|--------------|
| `tests/eventing/CC/test_eventing_rebalance_integration.yml` | `create_and_deploy`, `topology_change`, `pause`, `resume`, `undeploy_delete` |
| `tests/analytics/cheshirecat/test_analytics_integration_scale3.yml` | `analytics_setup`, `analytics_query`, `analytics_topology_change`, `analytics_teardown` |
| `tests/2i/cheshirecat/test_idx_cc_integration.yml` | `change_indexer_topologies` |

---

## Running the Test

```bash
./sequoia \
  -provider file:hosts.json \
  -skip_setup \
  -scope tests/integration/8.1/scope_8.1_magma.yml \
  -test tests/integration/8.1/test_8.1.yml
```

Against a fresh cluster (Docker provider):
```bash
./sequoia \
  -scope tests/integration/8.1/scope_8.1_magma.yml \
  -test tests/integration/8.1/test_8.1.yml
```

Use `-scale N` to multiply doc counts, scope/collection counts, and rate limits (default `scale=1`).

---

## Key Design Points

- **Two-cluster topology**: local (31 nodes, all services) + remote (6 data nodes) with 4 XDCR replications.
- **2 nodes held inactive** at start (`init_nodes: 29` out of 31) for use as rebalance-in targets throughout the test.
- **Conflict logging** is enabled on all XDCR replications, routing conflict logs to specific scopes/collections on the remote cluster.
- **Cross-cluster versioning (CCV)** is enabled on 4 local and 4 remote buckets before XDCR starts.
- **Vector search** is exercised on two dedicated buckets (10 and 11): bucket10 uses composite L2 indexes, bucket11 uses BHive indexes.
- **All buckets use Magma** storage with history retention enabled (bytes + seconds bounds vary by bucket).
- **Encryption at rest** is enabled on all local buckets except `bucket11`, with DEK rotation.
- **Topology stress** is applied to every service layer: data nodes (rebalance in/out/swap/failover), FTS nodes (failover, addback, rebalance out, rebalance in), eventing nodes (via referenced test), analytics nodes (via referenced test), and GSI nodes (via referenced 2i test).
- **Validation gates**: item count checks for XDCR, GSI, and FTS are run after workloads stop, before final index drops.

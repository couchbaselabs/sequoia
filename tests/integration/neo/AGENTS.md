# Integration Tests — Neo

Pre-Magma-era integration tests for Couchbase "Neo" (7.x pre-release) that served as the foundation before the versioned 7.2/7.6/7.7/8.x series. Multiple storage variants (Magma, Couchstore, Hybrid) and milestone-by-milestone decompositions allow targeted coverage. Compared to the later numbered releases, Neo tests use a larger remote cluster (8 nodes), lack history retention settings and bucket ranking, and enable audit logging — reflecting the features available at that time.

## What Changed Since Cheshirecat

| Area | Cheshirecat | Neo |
|------|------------|-----|
| Storage | Couchstore only | **Magma primary** + Couchstore + Hybrid variants |
| Scope variants | 3 (base / with-backup / eventing) | **5** (magma / with-backup-magma / hybrid / couchstore / no-gsi-n1ql) |
| Test decomposition | Single full tests + longevity | **Milestone files** (2/3/4) for partial runs |
| Audit logging | — | ✓ enabled |
| Remote cluster (primary scope) | 2 nodes | **8 nodes** (much larger XDCR target) |
| GSI OSO mode | — | Present but **disabled** (MB-43725 workaround) |
| Plasma in-memory compression | — | Present but **disabled** |
| CLI image | `couchbase-cli` (unversioned) | `couchbase-cli` (still unversioned) |
| Full scale-3 equivalent | `..._eventing_cbas_scale3.yml` | `test_neo_kv_..._scale3_magma.yml` |

**Summary:** Neo's primary contribution is Magma storage coverage, multi-storage variants (Hybrid, Couchstore), the milestone decomposition pattern, and a larger remote cluster to absorb higher XDCR throughput. Cluster configuration and bucket structure are otherwise the same as Cheshirecat-with-backup.

---

## Files

### Scope Files

| File | Storage | Local Nodes | Remote Nodes | Notes |
|------|---------|-------------|-------------|-------|
| `scope_neo_magma.yml` | All Magma | 31 (29 init) | **8** | Largest remote cluster; no history retention |
| `scope_neo_with_backup_magma.yml` | All Magma | 31 (29 init) | 2 | Adds `backup` service; smallest remote cluster |
| `scope_neo_hybrid.yml` | Mixed (Magma + Couchstore) | 31 (29 init) | 4 | Some buckets Couchstore, some Magma |
| `scope_couchstore.yml` | Couchstore / default | 30 (28 init) | 2 | Pure couchstore, slightly fewer nodes |
| `scope_neo_magma_wo_gsi_n1ql.yml` | All Magma | 31 (29 init) | varies | No GSI or N1QL services — KV/FTS/Eventing/Analytics only |

### Test Files

| File | Description |
|------|-------------|
| `test_neo.yml` | Base neo test (non-Magma scope) |
| `test_neo_magma.yml` | Full integration test for Magma scope |
| `test_neo_magma_milestone2.yml` | Magma: up through initial data load + GSI |
| `test_neo_magma_milestone3.yml` | Magma: adds FTS, Eventing, Analytics |
| `test_neo_magma_milestone4.yml` | Magma: adds topology changes + validation |
| `test_neo_couchstore.yml` | Full test for Couchstore scope |
| `test_neo_couchstore_milestone2.yml` | Couchstore milestone 2 |
| `test_neo_couchstore_milestone3.yml` | Couchstore milestone 3 |
| `test_neo_couchstore_milestone4.yml` | Couchstore milestone 4 |
| `test_neo_hybrid.yml` | Full test for Hybrid scope |
| `test_neo_hybrid_milestone2.yml` | Hybrid milestone 2 |
| `test_neo_hybrid_milestone3.yml` | Hybrid milestone 3 |
| `test_neo_hybrid_milestone4.yml` | Hybrid milestone 4 |
| `test_neo_magma_wo_gsi_n1ql.yml` | Test without GSI/N1QL nodes |
| `test_neo_kv_gsi_coll_xdcr_backup_sgw_fts_itemct_txns_eventing_cbas_scale3_magma.yml` | Full scale-3 run (equivalent to the versioned `8.x` style tests) |

---

## Scope Details

### `scope_neo_magma.yml` — Full Magma

**Local cluster (31 nodes, 29 init):**

| Service | Count | RAM |
|---------|-------|-----|
| Data | 16 | 90% |
| Index | 6 | 90% |
| Query | 2 | — |
| FTS | 2 | 85% |
| Eventing | 3 | 90% |
| Analytics | 3 | 90% |

No backup service. No history retention. No encryption.

**Remote cluster: 8 nodes** (4× larger than the later 7.6/7.7/8.x 2-node remote clusters — reflects the need for larger XDCR targets before Magma compaction efficiencies).

**Buckets (10 local, 4 remote):** Same names as later versions (`default`, `WAREHOUSE`, `NEW_ORDER`, `ITEM`, `bucket4`–`bucket9`, `remote`). No `historyretentionbytes`, no `rank`, no TTL on most buckets except `default` (TTL 3600 s) and `NEW_ORDER` (TTL 600 s). All Magma, fullEviction.

### `scope_neo_with_backup_magma.yml` — Magma with Backup

Same 31/29 local layout but with backup service (6 index, 2 query, 1 backup, 2 FTS, 3 eventing, 3 analytics). Remote cluster shrinks to **2 nodes**. Magma storage on all buckets. TTL on `default`, `WAREHOUSE`, `NEW_ORDER`, `bucket7`. Data path: `/data/couchbase`.

### `scope_neo_hybrid.yml` — Hybrid Storage

31/29 local, **4 remote** nodes. Mixed storage: `bucket4`, `bucket5`, `bucket6`, `bucket8`, `remote` use Magma; `default`, `WAREHOUSE`, `NEW_ORDER`, `ITEM`, `bucket7`, `bucket9` use default (Couchstore). Exercises cross-storage XDCR and index behavior.

### `scope_couchstore.yml` — Pure Couchstore

30 local nodes (28 init), 2 remote. No explicit `storage` fields — defaults to Couchstore. Higher memory allocation (90% data, 90% index, 85% FTS). No backup service. Used for pure couchstore baseline comparison.

---

## Test Structure: `test_neo_magma.yml`

### Key Differences vs Versioned 7.2+ Tests

| Feature | Neo Magma | 7.2+ |
|---------|----------|------|
| CLI image | `sequoiatools/couchbase-cli` (no version tag) | `couchbase-cli:7.2/7.6` |
| Audit logging | ✓ enabled | — |
| Shard affinity | — | 7.6+ only |
| History retention | — | 7.6+ only |
| Bucket rank | — | 7.6+ only |
| GSI OSO mode | Commented out (MB-43725) | ✓ |
| Plasma in-memory compression | Commented out (disabled) | — |
| Remote cluster | 8 nodes | 6 nodes (7.2–8.x) |

### Phase 1 — Cluster Configuration

1. Set tombstone purge interval (0.04, tighter than later 0.25)
2. Enable audit logging (log path `/data`, rotate 7 days)
3. Disable autofailover
4. Enable N2N encryption, set level `control`, IPv4 only
5. Re-enable autofailover (120 s, 1 node)
6. Enable Plasma Bloom Filter
7. Enable GSI redistribution on rebalance
8. Set FTS `bleveMaxResultWindow` → 100000, `bleveMaxClauseCount` → 2500

### Subsequent Phases

Same general flow as versioned tests: scope/collection setup → XDCR setup → data loading (catapult, pillowfight, gideon) → GSI/FTS create + build → eventing deploy + analytics setup → N1QL UDFs + queries → topology changes (rebalance out/swap, eventing/analytics topology, view attacks, XDCR filter, failover scenarios) → teardown and validation.

### Milestone Files

The milestone variants progressively build up the full test:

| Milestone | Coverage |
|-----------|---------|
| 2 | Through initial data load, initial GSI index creation |
| 3 | Adds FTS indexes, Eventing deploy, Analytics setup |
| 4 | Adds topology changes, failover scenarios, teardown/validation |

Full tests combine all milestones in one run.

### Cross-Referenced Tests

| File | Sections |
|------|---------|
| `tests/eventing/CC/test_eventing_rebalance_integration.yml` | `create_and_deploy`, `topology_change`, `pause`, `resume`, `undeploy_delete` |
| `tests/analytics/cheshirecat/test_analytics_integration_scale3.yml` | `analytics_setup`, `analytics_query`, `analytics_topology_change`, `analytics_teardown` |
| `tests/2i/cheshirecat/test_idx_cc_integration.yml` | `change_indexer_topologies` |

---

## Running

```bash
# Full magma run
./sequoia -provider file:hosts.json -skip_setup \
  -scope tests/integration/neo/scope_neo_magma.yml \
  -test  tests/integration/neo/test_neo_magma.yml

# Couchstore
./sequoia -provider file:hosts.json -skip_setup \
  -scope tests/integration/neo/scope_couchstore.yml \
  -test  tests/integration/neo/test_neo_couchstore.yml

# Hybrid
./sequoia -provider file:hosts.json -skip_setup \
  -scope tests/integration/neo/scope_neo_hybrid.yml \
  -test  tests/integration/neo/test_neo_hybrid.yml

# Partial run (milestone 2 only)
./sequoia -provider file:hosts.json -skip_setup \
  -scope tests/integration/neo/scope_neo_magma.yml \
  -test  tests/integration/neo/test_neo_magma_milestone2.yml
```

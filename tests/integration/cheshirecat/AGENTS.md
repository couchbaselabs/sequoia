# Integration Tests — Cheshirecat

Earliest integration test series in this directory, predating the Neo and versioned (7.2+) tests. Tests are named by cumulative feature coverage — each successive test file adds one more service to the previous. Three scope variants provide infrastructure for different service combinations. The `cheshirecat_with_backup_eventing` scope uses a different bucket-naming scheme (`bucket1`–`bucket9` rather than `WAREHOUSE`/`NEW_ORDER`/`ITEM`).

## Baseline Release

Cheshirecat is the **starting point** of the integration test series — there is no prior release to diff against. It establishes the conventions all later tests follow: two-cluster topology (local + remote), XDCR with compression, GSI + FTS + Eventing + Analytics + SGW, cumulative service naming, and teardown validation. Key characteristics that later releases improve upon:

- **Storage:** Couchstore (default) — no Magma, no history retention
- **Cluster size:** 30/28 local nodes, 2 remote — smallest of the series
- **No encryption at rest**, no bucket rank, no shard affinity, no audit logging
- **CLI:** unversioned `sequoiatools/couchbase-cli`
- **Tombstone purge interval:** 0.04 (tight, changed to 0.25 from 7.2 onward)
- **Test design:** cumulative-addition pattern and longevity variants established here

---

## Files

### Scope Files

| File | Nodes (local/init) | Remote | Backup | Storage | Notes |
|------|-------------------|--------|--------|---------|-------|
| `scope_cheshirecat.yml` | 30 / 28 | 2 | — | Couchstore (default) | No backup service; base scope |
| `scope_cheshirecat_with_backup.yml` | 31 / 29 | 2 | ✓ | Couchstore | Adds backup service + 2 extra nodes |
| `scope_cheshirecat_with_backup_eventing.yml` | 31 / 29 | 2 | ✓ | Mixed | Different bucket names; eventing source on `bucket1` |

### Test Files (Cumulative Service Addition)

| File | Services Covered | Scope to Use |
|------|-----------------|-------------|
| `test_cheshirecat_kv_gsi_coll_xdcr.yml` | KV, GSI, Collections, XDCR | `scope_cheshirecat.yml` |
| `test_cheshirecat_kv_gsi_coll_xdcr_backup.yml` | + Backup | `scope_cheshirecat_with_backup.yml` |
| `test_cheshirecat_kv_gsi_coll_xdcr_backup_sgw.yml` | + Sync Gateway | `scope_cheshirecat_with_backup.yml` |
| `test_cheshirecat_kv_gsi_coll_xdcr_backup_sgw_fts.yml` | + FTS | `scope_cheshirecat_with_backup.yml` |
| `test_cheshirecat_kv_gsi_coll_xdcr_backup_sgw_fts_itemct.yml` | + Item count validation | `scope_cheshirecat_with_backup.yml` |
| `test_cheshirecat_kv_gsi_coll_xdcr_backup_sgw_fts_itemct_txns.yml` | + Transactions | `scope_cheshirecat_with_backup.yml` |
| `test_cheshirecat_kv_gsi_coll_xdcr_backup_sgw_fts_itemct_txns_eventing.yml` | + Eventing | `scope_cheshirecat_with_backup.yml` |
| `test_cheshirecat_kv_gsi_coll_xdcr_backup_sgw_fts_itemct_txns_eventing_cbas.yml` | + Analytics (CBAS) | `scope_cheshirecat_with_backup.yml` |
| `test_cheshirecat_kv_gsi_coll_xdcr_backup_sgw_fts_itemct_txns_eventing_cbas_scale3.yml` | Full suite at scale factor 3 | `scope_cheshirecat_with_backup.yml` |
| `test_cheshirecat_kv_gsi_coll_xdcr_backup_sgw_fts_itemct_txns_eventing_cbas_scale3_foab.yml` | Full scale-3 + Failover and Add Back | `scope_cheshirecat_with_backup.yml` |
| `test_cheshirecat_longevity_no_eventing.yml` | Long-running longevity, no eventing | `scope_cheshirecat.yml` |
| `test_cheshirecat_longevity_no_eventing_scale3.yml` | Longevity at scale factor 3 | `scope_cheshirecat.yml` |

---

## Scope Details

### `scope_cheshirecat.yml` — Base (No Backup)

**Local cluster (30 nodes, 28 init):**

| Service | Count | RAM |
|---------|-------|-----|
| Data | 14 | 90% |
| Index | 6 | 90% |
| Query | 2 | — |
| FTS | 2 | 85% |
| Eventing | 3 | 90% |
| Analytics | 3 | 90% |

No backup service. Remote: 2 data nodes.

**Buckets (10 local, 4 remote):**

| Name | RAM | TTL | Storage | DDocs |
|------|-----|-----|---------|-------|
| `default` | 35% | 3600 s | default | `scale` |
| `WAREHOUSE` | 5% | — | default | — |
| `NEW_ORDER` | 5% | 600 s | default | — |
| `ITEM` | 5% | — | default | `all` |
| `bucket4` | 5% | — | default | — |
| `bucket5` | 5% | — | default | — |
| `bucket6` | 10% | 300 s | default | — |
| `bucket7` | 10% | — | default | — |
| `bucket8` | 5% | — | default | — |
| `bucket9` | 5% | — | default | — |
| `remote` | 80% | — | default | — |

No `historyretentionbytes`, no `rank`, no encryption. SGW on `bucket7`.

### `scope_cheshirecat_with_backup.yml` — With Backup

31/29 local nodes (adds 1 backup node). Remote: 2 data nodes. Same bucket layout as `scope_cheshirecat.yml` but `WAREHOUSE`, `NEW_ORDER` get `ttl: 3600`. Index RAM 50% (vs 90% in base). FTS RAM 80%.

### `scope_cheshirecat_with_backup_eventing.yml` — Eventing-Focused

31/29 local nodes with backup. Remote: 2 data nodes. **Different bucket names** — uses a generic numbered scheme:

| Name | RAM | TTL | Notes |
|------|-----|-----|-------|
| `default` | 35% | 3600 s | DDocs `scale` |
| `bucket1` | 5% | — | replaces `WAREHOUSE`; eventing source |
| `bucket2` | 5% | 600 s | replaces `NEW_ORDER` |
| `bucket3` | 5% | — | replaces `ITEM`, DDocs `all` |
| `bucket4`–`bucket9` | 5–10% | varies | same logical roles |
| `remote` | 80% | — | |

Data path: `/data` (not `/data/couchbase`). No SSH credentials defined. Used when the eventing test relies on specific bucket numbering that differs from the standard `WAREHOUSE`/`NEW_ORDER`/`ITEM` naming.

---

## Test Structure

### Cumulative Build Pattern

Each test file in the series adds exactly one service layer to the previous. This allows targeted debugging — if `test_cheshirecat_kv_gsi_coll_xdcr.yml` passes but `test_cheshirecat_kv_gsi_coll_xdcr_backup.yml` fails, the issue is in the backup integration. The canonical full-run is `..._eventing_cbas_scale3.yml`.

### Cluster Configuration (common to all tests)

Uses unversioned `sequoiatools/couchbase-cli` (older than 7.2). Tombstone purge interval 0.04 (tighter than Neo's). N2N encryption, IPv4 only. Plasma Bloom Filter. No shard affinity, no GSI OSO mode (predates those features).

### `scale3` Variants

Run with `-scale 3` to multiply document counts (catapult targets ×3), scope/collection counts, and query thread counts. Used for longevity and stress coverage.

### `foab` (Failover and Add Back)

Extends `scale3` with explicit failover-and-add-back topology change sequences — hard failover + delta/full recovery rebalance cycles under concurrent load.

### Longevity Tests

`test_cheshirecat_longevity_no_eventing.yml` and `_scale3.yml` are designed for extended runs (hours to days) without eventing to reduce complexity. They focus on data durability, XDCR convergence, and index consistency under continuous load and periodic topology changes.

---

## Running

```bash
# Minimal: KV + GSI + Collections + XDCR
./sequoia -provider file:hosts.json -skip_setup \
  -scope tests/integration/cheshirecat/scope_cheshirecat.yml \
  -test  tests/integration/cheshirecat/test_cheshirecat_kv_gsi_coll_xdcr.yml

# Full suite with all services at scale 3
./sequoia -provider file:hosts.json -skip_setup -scale 3 \
  -scope tests/integration/cheshirecat/scope_cheshirecat_with_backup.yml \
  -test  tests/integration/cheshirecat/test_cheshirecat_kv_gsi_coll_xdcr_backup_sgw_fts_itemct_txns_eventing_cbas_scale3.yml

# Longevity
./sequoia -provider file:hosts.json -skip_setup \
  -scope tests/integration/cheshirecat/scope_cheshirecat.yml \
  -test  tests/integration/cheshirecat/test_cheshirecat_longevity_no_eventing.yml
```

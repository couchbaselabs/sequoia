# GSI / Query upgrade test

One pre-upgrade test and one post-upgrade test that work for any initial -> final version pair.
The upgrade itself is done between the two runs by sequoia-provision `upgrade.sh`: online (rolling swap rebalance)
or offline (in place, one node at a time: stop, `dpkg -i`, start, wait until healthy). Both use the same order:
KV nodes first, then query/index nodes in a random order that `--swap-seed` replays.

| File | Run with |
|---|---|
| `scope_gsi_query_upgrade.yml` | both runs (`-scope`) |
| `test_gsi_query_pre_upgrade.yml` | `-version <initial>` |
| `test_gsi_query_post_upgrade.yml` | `-version <final> -skip_setup` |

Indexes, baseline queries and checks live in `containers/gsi_query_upgrade/` (image `sequoiatools/gsi_query_upgrade:dev`):
`index_spec.yml` (every index), `query_suite.yml` (every baseline query), `gsi_query_upgrade.py` (actions).

## Cluster

12 hosts in the provider file: nodes 1-4 data, 5-6 query, 7-11 index form the cluster (11 nodes);
node 12 is installed but kept out and is rebalanced in as an index node after the upgrade.

Bucket RAM quotas are percentages of the cluster quota and sum to 80% (20% headroom). Over 100% makes the last
`bucket-create` fail with "RAM quota ... too large" while sequoia carries on, and `apply_index_spec` then waits for
indexes on the missing bucket until its timeout. Keep the total at or below 80% when adding a bucket.

## Buckets, data and indexes

| Bucket | Collections | Docs | Writes | Indexes |
|---|---|---|---|---|
| `shoes_large` | `_default` | 5M shoes (dense `embedding`) | post-upgrade only | 5 scalar; 3 dense composite + 4 dense BHIVE (8.0+) |
| `shoes_static` | `_default`, `ss1.c1` | 100k each | never | per collection: 2 scalar; 1 dense composite + 1 dense BHIVE (8.0+) |
| `msmarco_sparse` | `_default`, `ms1.c1` | 1M each MSMARCO (sparse) | never | per collection: 2 scalar; 3 sparse composite + 2 sparse BHIVE (8.1+) |
| `hotel_mut` | `hm1.c1`, `hm1.c2` | 200k each Hotel | post-upgrade only | 13 on c1 (Hotel idx1-13), 6 on c2 |
| `hotel_static` | `hs1.c1`, `hs1.c2`, `hs1.empty_1`, `hs1.empty_2` | 200k, 200k, 0, 0 | never | 13 on c1, 2 on c2, 1 on each empty collection |
| `hotel_background` | `_default` | 100k Hotel | constant ~500 ops/sec, whole run (pre, upgrade, post) | 13 (Hotel idx1-13, 1 replica each); load only, never validated |
| `new_doctype` | `_default` | 0 | - | none yet (reserved for a new doc type) |
| `ddl_scratch` | `_default` | 10k Hotel (offline upgrades only) | - | none of its own; `run_ddl` creates and drops throwaway indexes |
| `plasma_holes` | `scope_0.coll_0` (scatter), `coll_1` (range), `coll_2` (keymove), `coll_3` (expiry), created by the test | 200k Hotel docs each (loaded only when it is used, see below) | holes made before the upgrade, then lightly written during the post-upgrade check | every scalar Hotel template per collection (`create_n_indexes_on_buckets`, 52, at most 1 replica; plus `ph_counter` on `coll_1`) |
| `bhive_churn` | `scope_0.coll_0`, `scope_0.coll_1` | 1M real BigANN vectors each (8.0+ sources only, not scaled) | churned before the upgrade, lightly written after | 1 scalar (`id`) + 1 dense BHIVE each |

95 indexes in total: 72 scalar/array (every version), 13 dense vector (8.0+), 10 sparse vector (8.1+; 8.1 was renamed 8.5, so builds reporting either work).
Replicas vary 0-4 per index and some scalar indexes are partitioned; the exact values are in `index_spec.yml`.
Indexes a version does not support are created after the upgrade, when the final version supports them.
Doc counts scale with `-scale`.

## Background workload (constant, whole run)

~500 ops/sec mutations on `hotel_background` (magmaloader, 1 worker), plus queries that are always index-backed
(sequential scans are disabled, so a query without a matching index would only fail):

- query_manager load only on collections that have the indexes its templates were written for: Hotel on
  `hotel_background` (all 13 Hotel indexes), dense vector on the shoes `_default` collections (8.0+), sparse on
  `msmarco_sparse._default` (8.1+). (query_manager only picks `scope_*`/`coll_*`/`_default` collections.)
- the test's own index-backed query suite (`run_suite`) on every bucket, started right after the baseline capture.

Lifetime:

- The pre-upgrade test starts them and never stops them. For an upgrade, Jenkins runs the pre-upgrade test with
  `-skip_cleanup`, so they keep running through the whole upgrade, including the mixed-version window.
- The post-upgrade test's first step removes them (a `docker:cli` container on the docker socket removes the running
  magmaloader / query_manager / gsi_query_upgrade containers), then `suite_report` reports the upgrade window:
  any static-bucket result that differed from the baseline fails, query errors during node swaps are warnings.
  It then starts the same workload again for its own run and stops it before the final checks.
- `hotel_background` is never validated.

## Index DDL while the cluster is mixed-version (offline upgrades only)

GSI does not allow DDL during a rebalance, so this only runs when `UPGRADE_MODE=offline`: an offline (in place, node by
node) upgrade has no rebalance, so DDL can run for the whole mixed-version window. Online runs skip it (the bucket is
not even loaded).

- The pre-upgrade test loads 10k Hotel docs into `ddl_scratch` and, as its last step, starts `run_ddl` (never stopped
  there, like the other background workload). It does nothing until the cluster is mixed-version (some nodes on a new
  version, some not), so it effectively runs only during the upgrade.
- Each round creates a deferred throwaway index (rotating scalar, partitioned, one replica), builds it, waits for it to
  come online, runs one query that uses it, and drops it, then pauses (`--ddl_pause`, 30 s).
- The post-upgrade test removes the container with the other background workload, then `ddl_report` warns on
  create/build/query/drop errors (an offline upgrade restarts every node in place, so lost KV / indexer / query
  connections are expected), fails only when a built index never came online, drops and reports an index left behind
  (a warning if its round failed or was interrupted by the removal, a failure otherwise), and warns if no round ran in
  the mixed-version window.

## Plasma holes (CBSE-23065, MB-65842, MB-68945)

An indexer recovering persisted plasma pages after an upgrade must still recognise pages that were already empty (the
empty-page flag was lost on recovery before 7.6.10 / 8.0.0, so the hole cleaner never merged them and the indexer
ended up at its memory quota with resident ratio 0%). It only applies where persisted indexes are recovered, so the steps run
for `UPGRADE_MODE=offline` and for `online` with `ENABLE_SHARD_AFFINITY=true` on a 7.6+ source (a plain online upgrade
rebuilds the indexes on new nodes and carries no holes over). "7.6+ source" is the version the cluster started on: the
pre-upgrade steps use `.Version` for that, the post-upgrade steps use `UPGRADE_SOURCE_VERSION`, because `.Version` is the final
version there (using it ran the post-upgrade plasma steps on a 7.2 source that had made no holes, series 11, #21). All of it is in the new bucket `plasma_holes`; in the other modes its
bucket stays empty (nothing is created in it).

The docs are plain Hotel docs (magmaloader), the holes come from magmaloader (`--delete_mode`, `--expiry_mode`) and the generic
**indexmanager** actions `churn_keyspaces` and `report_storage_stats` (plus the existing `create_n_indexes_on_buckets`,
`build_deferred_index` and `wait_until_mutations_processed`), so other GSI tests can use them; the upgrade-specific
judgement (before / after) stays in `gsi_query_upgrade` and works on the JSON files `report_storage_stats` writes
(`{captured_at, prefix, instances, timeline}`).

Pre-upgrade (`plasma_holes`: collections, load and indexes first, then the holes):

1. `sequoiatools/collections` creates `scope_0.coll_0` .. `coll_3`; magmaloader loads 200k Hotel docs into each (`counter` follows
   the key, `price` is random); `create_n_indexes_on_buckets --num_of_indexes_per_bucket 52 --set_max_replicas 1` creates every
   scalar Hotel template on the four collections and `build_deferred_index` builds the deferred ones. `coll_3` is loaded with
   `--expiry_mode true --percentage_expiry 90 --max_ttl 1800`: the last 90% of its docs get a 30 minute TTL at creation. TODO: tune
   that TTL after the next run (it must outlast the load, the index creation and the builds, or there are no holes);
2. the holes, one pattern per collection: `scatter` (`coll_0`) and `range` (`coll_1`) are `magmaloader --delete_mode true` over
   the first 90% of the keys, a contiguous block of documents. What differs is the index: the Hotel indexes start with fields
   unrelated to the key (`price`, `city`, ...), so the delete leaves scattered holes in every page (scatter); `ph_counter` on `counter`
   (a standalone `CREATE INDEX` through `sequoiatools/cbq` on `coll_1`) follows the key, so the same delete empties whole pages of it (range; `counter` is only approximately the key, so a few pages
   stay partly full, and it is the one index that matters on `coll_1`). `keymove` (`coll_2`) is `churn_keyspaces keymove` on
   `price` (adds 10000 to `price` below 1850, about 90% of the docs: their entries leave the old range and fill a new one),
   `expiry` (`coll_3`) is the TTL above;
3. `wait_until_mutations_processed`, then `report_storage_stats --wait_empty_pages 1`: the purger and hole finder act 10 to 20
   minutes after such a churn (seen on a small node: ~20 minutes of `mvccPurger` runs that purged nothing, then pages fell and
   the first empty pages appeared), so it reads every minute for up to 40 minutes until empty pages exist (7.6.9+) or, where the
   indexer does not report them, purges have happened. A timeout is a warning;
4. `capture_plasma_state`: checks the holes are there and keeps the page counts and hole stats per instance from
   `GET :9102/stats/storage` (`Stats.MainStore`: `num_pages`, `items_count`, `num_empty_pages`, `hf_num_*`, `merges_emptypages`,
   `purges`, ...). The density is `items_count / num_pages`, not `total_records / num_pages`: `total_records` keeps the unpurged
   delete records, so it looks healthy (about 280) while a page holds 15 live items. BHIVE / vector instances have no
   `num_pages` and are left out.

Post-upgrade, up to ~45 minutes (steps after `wait_for_indexes`):

- `report_storage_stats` right after the upgrade; then 20 minutes of reads with no scans; `plasma_scans` (a full scan of every
  index); 20 more minutes of reads (MB-65842's two checks);
- 5 minutes of light writes (`churn_keyspaces touch`), then `wait_until_mutations_processed`: the indexers must drain every
  mutation (not drained = writers throttled, the Citi symptom: that container fails); then a 20 minute watch (`report_storage_stats
  --watch_seconds 1200`), because the purger and the hole cleaner are driven by writes (series 12, #25: no `mvccPurger` run in the 40
  idle minutes before the writes, and the empty pages stayed flat; the empty-page warning is judged at the end of this watch and
  says whether the empty pages fell during it);
- `validate_plasma` judges the files: every collection still has its instances and the same indexed item count (a mismatch
  fails); empty pages that are still there afterwards, no merge or hole-finder activity, or a density below half of the
  pre-upgrade one are warnings (`--plasma_fail_on_empty true` makes the first a failure). The thresholds are guesses to be
  set from real runs. `validate_plasma` fails when the pre-upgrade snapshot is missing.

## BHIVE churn and recall (8.0+ sources)

BHIVE indexes are Magma-backed: they have no plasma pages, so the empty-page checks above do not apply (their `/stats/storage`
entries carry `item_count`, `approx_total_records`, `total_data_size`, `purge_ratio`). What a newer index type can still get wrong
across an upgrade is silent: recall and space. The data is real BigANN, loaded by `magmaloader --sift_path` into two collections of
`bhive_churn` (named `scope_0` / `coll_*` because query_manager only picks those), 1M vectors each. The loader (DocLoader
`siftBigANN`) sets the filter fields by id range, so the filter `size=5` of the `shoes_1M` query selects exactly ids 0 to 1M and the
BigANN groundtruth `idx_1M.ivecs` is exact for them.

Pre-upgrade, after the indexes are built:

1. recall reading 1: `query_manager` for 5 minutes, `--template shoes_1M --nprobe 50 --validate_vector_query_results true
   --recall_file ...` (nprobe fixed at 50 for every run);
2. indexmanager `churn_keyspaces` (SQL++, because SIFTLoader's delete does nothing): `coll_0` loses 50% of its vectors spread over the key range,
   `coll_1` the first 50%;
3. `magmaloader --sift_reload true` for both collections: DocLoader's create is an insert (an existing key fails) and its update
   is an upsert, so the reload goes through the update path with `-mutate 0` (the existing `--mutations_mode` uses `-mutate 5`,
   which shifts every vector). The same vectors and fields come back, the end state is the original 1M, and the groundtruth applies again;
4. `wait_for_docs` (1M back), `wait_until_mutations_processed`, `report_storage_stats` (name filter `bhive`: item_count, approx_total_records,
   total_data_size, purge_ratio per instance) and `capture_bhive_state` (checks 1M indexed items per collection, keeps the totals);
   then recall reading 2. `compare_recall` of the two readings is a warning only (that is churn, not the upgrade).

Post-upgrade: `report_storage_stats` right after the upgrade, a 15 minute watch on data size and purge ratio, 5 minutes of light writes
(`churn_keyspaces touch`) that the indexers must drain (`wait_until_mutations_processed`), a last read, and `validate_bhive` (same
indexed items as before, a warning if the data size grew beyond 1.5x); then recall reading 3 and `compare_recall` of readings 2 and 3
(a mean recall that falls by more than 2 points warns, by more than 10 fails). The post steps are gated on `UPGRADE_SOURCE_VERSION`
(exported by the Jenkinsfile) and `validate_bhive` fails when the pre-upgrade snapshot is missing. The BHIVE indexes are marked
`only_if_loaded` in `index_spec.yml`, so `apply_index_spec` leaves them alone while the collections are empty (a BHIVE index cannot
train without data; an upgrade from a 7.x source would otherwise create them on empty collections).

Recall reading 3 is wrapped in `completed_requests --cr_mode start` / `stop` / `report`: for the length of the reading the query
service keeps every request in `system:completed_requests` (threshold 0, limit 50000; normally only requests over 1000 ms are kept),
the previous values are restored afterwards, and the report lists the vector requests that returned no rows and no error (request id,
node, time, consistency, phase counts, the plan EXPLAIN gives now) and writes them in full to
`/data/gsi_query_upgrade_completed_requests_report.json`. Series 12 (#26) had 2 of 14 such executions (20-56 ms) that were not
recorded anywhere.

## Pre-upgrade (`-version <initial>`): setup and capture

No faults, no topology changes; only the background workload runs.

1. Indexer setting `redistribute_indexes`. Optionally `enable_shard_affinity` (file-based index rebalance): only
   when `ENABLE_SHARD_AFFINITY=true`, `UPGRADE_MODE=online` and the initial version is 7.6+ (off by default: set
   `ENABLE_SHARD_AFFINITY: true` in the sequoia-provision upgrade job's `TEST_ENV`, which forwards it to the pre- and
   post-upgrade runs as an env var).
2. Load all buckets in parallel, then `wait_for_docs` until every collection has its full doc count and the
   count is stable, so vector indexes train on the fully loaded `shoes_large` / `msmarco_sparse`.
3. `apply_index_spec`: every index the initial version supports, built in stages of at most 16 index instances
   (replicas included, `--max_concurrent_builds`), each stage online before the next.
4. Query features:
   - sequential scans disabled (7.6+), so every query must be index-backed
   - fixed UDFs used by the baseline (SQL++ `hotel_static.hs1.upq_price_band`, JavaScript `upq_label`)
   - query_manager UDFs on `hotel_mut` (`create_n1ql_udf`, `create_udf`, `run_udf_queries`)
   - AWR + automatic update statistics (8.0+)
5. `item_count_check` on every bucket.
6. `UPDATE STATISTICS` on every collection, empty ones included (the stats the upgrade has to migrate), right
   before the capture; fails if any collection has no stats stored (`N1QL_SYSTEM_BUCKET.N1QL_SYSTEM_SCOPE.N1QL_CBO_STATS`,
   or `<bucket>._system._query` on versions that keep them there). Not `system:dictionary`: that only lists what the
   answering query node has cached.
7. Plan stability `prepared_only` (8.1+).
8. `capture_baseline` -> `/data/gsi_query_upgrade_baseline.json`: per query in `query_suite.yml` the EXPLAIN plan
   summary (indexes, join method, covering vs fetch, sort, CBO-costed or not), row count, median latency, a result
   hash (exact queries on static buckets only) and a named PREPARE. Queries needing a newer version are stored as
   deferred. `QUERY_METADATA` is checked for persisted plans (8.1+).
9. `capture_index_names` -> `/data/gsi_query_upgrade_indexes.json`.
10. cbcollect of the pre-upgrade cluster: `sequoiatools/logcollector --iterations 1 --collect_only true --customer_name
    upgrade-pre` (cluster-wide, uploaded to `cb-engineering.s3.amazonaws.com/upgrade-pre/`; the bundle URLs are in the step's
    console output). Taken before `upgrade.sh` reinstalls any node, whose logs are gone afterwards.

## Post-upgrade (`-version <final> -skip_setup`)

1. Before anything writes:
   - `wait_for_indexes`: every index instance `Ready` again. After an offline (in-place) upgrade each indexer has
     restarted and recovers its indexes from disk before serving scans; after an online upgrade this returns at once.
   - `validate_index_names`: no index instance lost.
   - Offline upgrade only: indexmanager `report_indexer_warmup_times` prints how long each indexer took to warm up
     (recover its indexes from disk) after its in-place restart, from `Status Warmup` -> `Status Active` in
     `indexer.log*` on every index node (over SSH as root, like the Totoro test). Only warmups that started after the
     pre-upgrade `capture_index_names` snapshot are listed (`--since_snapshot`), so the install-time first starts are
     left out. Report only, no limit: the action exits 1 on purpose so sequoia dumps the report (`expect_error`).
     Nothing to report for an online upgrade (the swapped-out nodes and their logs are gone).
   - `validate_statistics`: on every query node, a query on every keyspace (empty ones included) that filters on
     an indexed field with statistics (`WHERE <field> IS NOT NULL`, so CBO has to read them) returns within 120s
     (CBSE-23292 deadlock; a plan not costed by CBO is a warning), every keyspace that had CBO stats still has
     them, `UPDATE STATISTICS` still completes.
   - `validate_baseline`: plan diff per query (CBSE-22341 / 23025 / 21247), result hash on every query node,
     latency warning above 3x, every named prepared statement executes with the baseline results on every query
     node and with the expected plan (pinned plan when plan stability is on; current optimizer plan otherwise,
     CBSE-21288), UDFs still present, sequential scans still disabled, plan stability and `QUERY_METADATA`
     records kept. A plan whose only difference is whether CBO costed it is a warning, not a failure. So is any
     EXPLAIN plan change from a source older than 7.6 (CBO is off by default there, so the join order can change
     by design; results and latency are still checked). A prepared
     statement that keeps a plan different from the current optimizer plan is a warning when the source version
     is older than 7.6 (CBO is off by default there and on from 7.6, so the join order can change by design; a
     prepared plan is only re-prepared automatically when the opt-in `n1ql-feat-ctrl` bit 23 is set, which
     production does not do and this test leaves unset, MB-63204). On an 8.0+ final version the check then runs
     `UPDATE system:prepareds UNSET planPreparedTime`, re-executes the statement on every query node and fails if
     it returns different results than the baseline or still serves the stale plan. From a 7.6+ source a changed
     prepared plan still fails, with one exception: `equivalent_indexes` in `index_spec.yml` lists index templates that serve
     the suite equally (now `idx4` and `idx7`: both lead with `price` and cover the same queries). A plan, or a prepared plan,
     that only swaps one for the other is a warning (`EQUIV-INDEX` / `STALE-EQUIV`); the covered flag, the scan operator, the
     keyspace and everything else in the plan still count, so a swap to an index that stops covering still fails (series 11, #23:
     ten `hotel_static.hs1.c1` queries went from `idx7` to `idx4` on 8.0.3 -> 8.5). Deferred
     queries are left to `run_suite` (step 3), which runs after `apply_index_spec` creates their indexes.
     Prepared statement survival (`--expect_prepared_survive`, default `auto`): prepared statements live only
     in memory and a restarted query node copies them from another query node, so they survive an upgrade
     that restarts one query node at a time and are lost when every query node restarts at once. Before
     re-preparing anything, the check reads `system:prepareds` on every query node: if every node lost all of
     them it warns; if some were lost while others survived it fails (priming from a peer failed). `true` fails
     on any loss, `false` only warns. The post YAML passes `--upgrade_mode={{env `UPGRADE_MODE`}}` (the
     Jenkinsfile exports `UPGRADE_MODE`): `online` or `offline` turns `auto` into `true`, since `upgrade.sh`
     restarts one query node at a time in both modes. Lost statements are re-prepared on the node that lost them.
   - query_manager `run_udf_queries`.
2. `apply_index_spec` adds indexes the final version newly supports, `UPDATE STATISTICS`, AWR/AUS (8.0+),
   `capture_index_names` -> `/data/gsi_query_upgrade_indexes_post.json`.
3. Writes on `shoes_large` and `hotel_mut` (magmaloader mutations, each writer at a random 1 to 1000 ops/sec: the rate is in the console command line); queries on every bucket: `run_suite` loops the baseline suite (static
   results must keep matching the baseline hash) plus query_manager workloads (Hotel on `hotel_mut`, dense vector
   on the shoes buckets 8.0+, sparse on `msmarco_sparse` 8.1+).
4. Rebalance-in node 12 as an index node, `validate_index_names`.
5. Rebalance-out the first index node, `validate_index_names`.
6. Stop workloads, `wait_until_mutations_processed`, `item_count_check` on every bucket, `suite_report` (fails on
   any result mismatch or query error seen during the run), `run_udf_queries`.
7. cbcollect of the upgraded cluster (`--customer_name upgrade-post`, same as the pre step). This replaced a 90 minute idle
   step that waited for eagle eye to collect post-upgrade logs.

## Test depth (`UPGRADE_DEPTH`)

`UPGRADE_DEPTH=full` (default, also when unset) runs everything. `UPGRADE_DEPTH=quick` (exported by the sequoia-provision
Jenkinsfile; `Jenkinsfile_upgrade_series` has the same parameter and applies it to every path) keeps the setup, the data load, the
index spec, the query features, the baseline, the background workload and DDL through the upgrade, and the post-upgrade
validations (`suite_report` of the upgrade window, `ddl_report`, `wait_for_indexes`, warmup report, index names,
statistics, baseline, prepared statements, UDFs, new-version indexes, item counts, UDF queries, cbcollect). It skips:

- plasma holes: collections, load, indexes, churn, capture (pre) and the readings, scans, light writes, `validate_plasma` (post)
- BHIVE churn and recall: the `bhive_churn` load and wait, readings, churn, reload (pre) and readings, `validate_bhive`,
  `completed_requests`, `compare_recall` (post)
- the post-upgrade writes, the 2 h `run_suite`, the rebalance-in and rebalance-out, and the matching final `suite_report`

A step skipped this way has its `requires` combined with `ne (env `UPGRADE_DEPTH`) `quick``. Remember that a step with
no `image:` and no `requires:` inherits both from the step before it, so a new step added after a gated one needs its
own `requires`.

## How to run

One build of the sequoia-provision Jenkins pipeline runs the whole flow:

1. `deploy.sh` installs `CB_VERSION` / `CB_BUILD` on the pool (12 hosts).
2. Pre-upgrade sequoia run: `TEST_FILE` = `tests/upgrade/gsi_query/test_gsi_query_pre_upgrade.yml -scope tests/upgrade/gsi_query/scope_gsi_query_upgrade.yml`.
3. `upgrade.sh` with `UPGRADE_MODE` = `offline` or `online` (`UPGRADE_SPARE_HOSTS` for online) to
   `UPGRADE_CB_VERSION` / `UPGRADE_CB_BUILD`; it also installs the final version on node 12 and rewrites
   `provider.yml` with the post-upgrade membership.
4. Post-upgrade sequoia run: `POST_UPGRADE_TEST_FILE` = the post test with the same `-scope`, `-version UPGRADE_CB_VERSION -skip_setup`.

To re-run only the post phase on an already upgraded cluster: `SKIP_INSTALL=true`, `UPGRADE_MODE=none`,
`SKIP_SETUP=true`, `TEST_FILE` = post test, `CB_VERSION` = final version.

Locally:

```bash
./sequoia -provider file:provider.yml -version 7.6.5 -scope tests/upgrade/gsi_query/scope_gsi_query_upgrade.yml -test tests/upgrade/gsi_query/test_gsi_query_pre_upgrade.yml -skip_teardown
# upgrade the cluster (sequoia-provision: ./upgrade.sh --mode offline --cb-version 8.5.0 --cb-build <build>)
./sequoia -provider file:provider.yml -version 8.5.0 -skip_setup -scope tests/upgrade/gsi_query/scope_gsi_query_upgrade.yml -test tests/upgrade/gsi_query/test_gsi_query_post_upgrade.yml
```

Both runs must use the same sequoia client host: the snapshots are written to its `/data`.
Data prerequisites on that host (same as the other GSI tests): `/data/bigann/` (shoes) and `/data/sparse/collection.vecs` (MSMARCO).

## Extending

- New doc type: load it into `new_doctype`, add its keyspace and indexes to `index_spec.yml` and its queries to
  `query_suite.yml`, then rebuild the image.
- TODO (low priority): CBSE-21288 sequential-scan privilege. The CBSE was closed as expected behaviour: a prepared
  statement created by a user with the sequential-scan privilege keeps its sequential-scan plan, and a user without
  `query_use_sequential_scans` gets error 13014 when executing it; it only showed after the 7.6 upgrade because 7.6
  introduced sequential scans. This test disables sequential scans and keeps every query index-backed, so it cannot
  hit it. If wanted, add a separate flagged check (not in every path) on a 7.6+ source with sequential scans left
  enabled: Administrator prepares a statement with no matching index, a non-admin user gets 13014 before and after
  the upgrade, and creating the index and deleting the entry from `system:prepareds` makes it re-prepare.
  Everything currently runs as Administrator.

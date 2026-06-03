# Backup and Restore Tests

## Directory Contents

| File | Purpose |
|------|---------|
| `test_backup_restore_nfs.yml` | Full system test — NFS storage at `/mnt/nfs_data/test_system_backup` |
| `test_backup_restore_s3.yml` | Same test structure — S3 bucket `s3://backup-restore-system-test/backups` |
| `test_backup_restore_azure.yml` | Same test structure — Azure Blob `az://backup-restore-system-test/backups` |
| `test_backup_restore_gcp.yml` | Same test structure — GCP bucket `gs://backup-restore-system-test/backups` |
| `test_backup_restore_local.yml` | Lighter test — local filesystem storage |
| `scope_backup_restore_magma.yml` | Scope: all-magma bucket storage |
| `scope_backup_restore_mix.yml` | Scope: mixed magma + couchstore bucket storage |

## Storage Variant Differences

All test files share the same four sections and backup strategy logic. The differences are:

| Variant | Archive path | Template suffix | Cleanup section |
|---------|-------------|-----------------|-----------------|
| NFS | `/mnt/nfs_data/test_system_backup` | _(none)_ | No pre-clean needed |
| S3 | `s3://backup-restore-system-test/backups` | `_aws` | Has `cleanup_existing_repos` section |
| Azure | `az://backup-restore-system-test/backups` | `_azure` | Has `cleanup_existing_repos` section |
| GCP | `gs://backup-restore-system-test/backups` | `_gcp` | Has `cleanup_existing_repos` section |
| Local | local path | _(none)_ | No pre-clean needed |

GCP uses service account JSON (`$GOOGLE_APPLICATION_CREDENTIALS` → `--obj-auth-file`) rather than access/secret key pairs. S3 uses `--obj-access-key-id`/`--obj-secret-access-key` with `$AWS_ACCESS_KEY_ID`/`$AWS_SECRET_ACCESS_KEY`. Each cloud variant sources its corresponding `/etc/profile.d/<cloud>_credentials.sh` on the SSH host.

When modifying a test for one variant, apply the same change to the others unless it is storage-specific.

## Test Sections

Each test file is divided into four sections (`section_start` / `section_end`):

1. **`initial_data_load`** — Tombstone compaction config, create scopes/collections, seed data via Gideon (default collection) and magmaloader (all collections).
2. **`incremental_backup_merge`** — Continuous incremental backups, periodic merges, chaos tests (kill memcached / cbbackupmgr, stop couchbase), restore cycles.
3. **`incremental_backup_full`** — Multiple backup chains (`systemtestbackup1`–`5`); each major topology event starts a new full backup instead of merging.
4. **`full_backup`** — One new full backup repo per topology event (`systemtestbackup6`–`18`); no incrementals.

## Key Patterns

### Backup repo naming
- NFS/Local: `systemtestbackup`, `systemtestbackup1` … `systemtestbackup18`
- S3/Azure: `systemtest`, `systemtest1` … (shorter prefix)

### Templates — always use the correct variant
```yaml
# NFS / Local
template: configure_backup_repo
template: backup_cluster
template: restore_backup
template: resume_backup_cluster
template: purge_backup_cluster
template: resume_restore_backup
template: purge_restore_backup
template: clean_backup_repo

# S3 — suffix _aws
template: configure_backup_repo_aws
template: backup_cluster_aws
# ...same suffix pattern

# Azure — suffix _azure
template: configure_backup_repo_azure
template: backup_cluster_azure
# ...same suffix pattern

# GCP — suffix _gcp
template: configure_backup_repo_gcp
template: backup_cluster_gcp
# ...same suffix pattern
```

### Topology change pattern
Every topology change follows: wait (600 s) → change → wait → take backup. Keep this order when adding new topology steps.

### Chaos test pattern
```yaml
# Non-blocking op that may fail
template: <operation>_wo_wait   # or expect_error: true
# Wait for failure window
image: sequoiatools/cmd
entrypoint: sleep
command: "60"
wait: true
# Inject failure
template: kill_process
args: "{{.Nodes | .Service `kv` | net N}}, <process>"
# Recover / resume / purge
template: resume_backup_cluster  # or purge_backup_cluster
```

### Stop-couchbase chaos pattern
The stop-couchbase-during-backup chaos test stops couchbase on **two nodes** (net 3 and net 2) for resilience. A 900 s wait precedes the stop. After recovery, a `rebalance_in` step returns the cluster to its original topology before the next backup:
```yaml
# Stop two nodes — net 3 first, then net 2
template: stop_couchbase
args: "{{.Nodes | .Service `kv` | net 3}}"
# start both back
template: start_couchbase
args: "{{.Nodes | .Service `kv` | net 3}}"
template: start_couchbase
args: "{{.Nodes | .Service `kv` | net 2}}"
# then rebalance_in before continuing
template: rebalance_in
```

### Magmaloader key ranges
Each section uses a non-overlapping `--start` offset so doc keys never collide across sections. When adding a new section, continue from the previous section's end range.

### Docker image conventions
- SSH/remote commands: `sequoiatools/cmd` (not `vijayviji/sshpass` — deprecated)
- KV load: `sequoiatools/gideon_latest`
- Collection load: `sequoiatools/magmaloader`
- CLI operations: `sequoiatools/couchbase-cli:8.1`
- Backup manager: `sequoiatools/cbbackupmgr`

## Data Loaders

| Loader | Image | Target | Op mix |
|--------|-------|--------|--------|
| Gideon | `sequoiatools/gideon_latest` | Default collection only | 35% create / 30% update / 20% delete / 15% expire |
| Magma | `sequoiatools/magmaloader` | All collections (skip default) | 35c / 30u / 20d / 30% expiry |

Initial seed uses 100% create. Background loaders use the mixed ratios above.

## Chaos Test Matrix

| Scenario | Failure point | Recovery |
|----------|--------------|----------|
| Kill memcached during rebalance | Rebalance | Retry rebalance |
| Kill memcached before backup | Pre-backup | Wait for auto-restart |
| Stop couchbase during backup | During backup | Start service + resume |
| Kill memcached during backup | During backup | Resume backup |
| Kill memcached during backup | During backup | Purge + restart |
| Kill cbbackupmgr during backup | During backup | Resume backup |
| Kill memcached before restore | Pre-restore | Wait + restore |
| Kill cbbackupmgr during restore | During restore | Resume restore |
| Kill cbbackupmgr during restore | During restore | Purge restore |

## Key Templates Reference

| Template | Purpose |
|----------|---------|
| `configure_backup_repo` | Initialize backup repository (NFS/local) |
| `configure_backup_repo_aws` | Initialize backup repository (S3) |
| `configure_backup_repo_azure` | Initialize backup repository (Azure) |
| `configure_backup_repo_gcp` | Initialize backup repository (GCP) |
| `backup_cluster` | Take incremental or full backup (NFS/local) |
| `backup_cluster_aws` | Take incremental or full backup (S3) |
| `backup_cluster_azure` | Take incremental or full backup (Azure) |
| `backup_cluster_gcp` | Take incremental or full backup (GCP) |
| `resume_backup_cluster` | Resume a failed backup (NFS/local) |
| `resume_backup_cluster_aws` | Resume a failed backup (S3) |
| `resume_backup_cluster_azure` | Resume a failed backup (Azure) |
| `resume_backup_cluster_gcp` | Resume a failed backup (GCP) |
| `purge_backup_cluster` | Purge failed backup state (NFS/local) |
| `purge_backup_cluster_aws` | Purge failed backup state (S3) |
| `purge_backup_cluster_azure` | Purge failed backup state (Azure) |
| `purge_backup_cluster_gcp` | Purge failed backup state (GCP) |
| `restore_backup` | Restore from backup (NFS/local) |
| `restore_backup_gcp` | Restore from backup (GCP) |
| `resume_restore_backup` | Resume a failed restore (NFS/local) |
| `purge_restore_backup` | Purge failed restore state (NFS/local) |
| `clean_backup_repo` | Delete a backup repository (NFS/local) |
| `clean_backup_repo_aws` | Delete a backup repository (S3) |
| `clean_backup_repo_azure` | Delete a backup repository (Azure) |
| `clean_backup_repo_gcp` | Delete a backup repository (GCP) |
| `rebalance_out` | Remove node (blocking) |
| `rebalance_out_wo_wait` | Remove node (non-blocking) |
| `rebalance_in` | Add node (blocking) |
| `rebalance` | Trigger rebalance |
| `failover_node` | Graceful failover |
| `hard_failover_node` | Hard failover |
| `recover_node` | Recover failed node (`delta` or `full`) |
| `autofailover1Node` | Trigger auto-failover |
| `kill_process` | Kill named process on a node |
| `enable_autofailover` | Set auto-failover timeout |
| `create-multi-scopes-collections` | Create scope/collection hierarchy |

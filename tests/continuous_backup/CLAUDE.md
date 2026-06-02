# Continuous Backup / PITR Tests

## Key Concepts

**Continuous backup** captures every mutation via `cbcontbk`, enabling **Point-in-Time Recovery (PITR)** to any timestamp — not just backup snapshots. This is distinct from the traditional backup/restore tests in `tests/backuprestore/`.

Timestamps are recorded before and after every topology change to `/tmp/timestamps.txt` on the arbiter node. The `sequoiatools/pitr` tool reads this file to drive PITR restore validation.

## Directory Contents

| File | Purpose |
|------|---------|
| `test_cont_backup_restore_nfs.yml` | Full system test — NFS storage |
| `test_cont_backup_restore_s3.yml` | Same test — S3 cloud storage |
| `test_cont_backup_restore_azure.yml` | Same test — Azure Blob storage |
| `scope_backup_restore_nfs.yml` | Scope for NFS test (magma storage) |
| `scope_backup_restore_cloud.yml` | Scope for S3/Azure tests (magma storage) |

Both scopes use magma-only bucket storage.

## Storage Variant Differences

| Variant | Backup archive | Cont-backup location | Extra section |
|---------|---------------|----------------------|---------------|
| NFS | `/mnt/nfs_data/test_system_backup` | `/mnt/nfs_data/test_system_continuous_backup` | — |
| S3 | `s3://backup-restore-system-test/backups` | `s3://cont-bkp-system-test/systemtest/` | `setup_cloud_backup` |
| Azure | `az://backup-restore-system-test/backups` | `az://cont-bkp-system-test/systemtest/` | `setup_cloud_backup` |

Cloud variants add a `setup_cloud_backup` section (before `initial_data_load`) that:
1. Disables auto-failover
2. Registers cloud credentials via the REST API
3. Enables continuous backup on each bucket with `continuousBackupEnabled=true` and a cloud credential ID
4. Re-enables auto-failover

When modifying one variant, apply the same change to others unless it is storage-specific.

## Test Sections

NFS has 3 sections; S3/Azure have 4 (they prepend `setup_cloud_backup`):

1. **`setup_cloud_backup`** _(S3/Azure only)_ — Register cloud credentials, enable continuous backup per bucket.
2. **`initial_data_load`** — Compaction config, create scopes/collections, seed via Gideon + magmaloader.
3. **`single_backup_pitr`** — Take one baseline backup, run topology changes with timestamp recording, chaos tests against `cbcontbk`, then multiple PITR restore cycles.
4. **`incremental_backup_pitr`** — Interleave incremental backups with topology changes + timestamps, chaos tests, then PITR restore cycles.

## Key Patterns

### Timestamp recording
Record a timestamp before and after every topology change. The PITR tool reads these from the arbiter node:
```yaml
image: sequoiatools/cmd
command: "sshpass -p {{.SSHPassword}} ssh -o StrictHostKeyChecking=no
          {{.SSHUsername}}@{{.Nodes | .Service `arbiter` | net 0}}
          'date +%s >> /tmp/timestamps.txt'"
wait: true
```
Initialize at the start of each section: `rm -f /tmp/timestamps.txt && touch /tmp/timestamps.txt`

### Enabling / disabling continuous backup
Must be disabled before bucket flush; re-enabled before the next data loading phase:
```yaml
image: sequoiatools/couchbase-cli
command: "bucket-edit -c {{.Orchestrator}}:{{.RestPort}} --bucket {{.Bucket}}
          -u {{.RestUsername}} -p {{.RestPassword}} --continuous-backup-enabled 0"
```

### PITR restore invocation
```yaml
image: sequoiatools/pitr
command: --num_timestamps <N> --mode <MODE>
         --ssh-host {{.Nodes | .Service `arbiter` | net 0}}
         --ssh-user {{.SSHUsername}} --ssh-password {{.SSHPassword}}
         --cluster-ip {{.Orchestrator}}
         --rest-user {{.RestUsername}} --rest-password {{.RestPassword}}
         --archive <archive-path> --repo systemtestbackup
         --cont-backup-location <cont-backup-path>
         --threads 8 --tmp-dir /data/tmp
# Cloud variants add: --storage-type aws|azure --obj-staging-dir /data/s3
# Resume:  add --resume
# Purge:   add --purge
```

### cbcontbk chaos pattern
```yaml
# Inject failure (expect_error or non-blocking op)
template: kill_process
args: "{{.Nodes | .Service `kv` | net N}}, cbcontbk"
# Wait for auto-restart (cbcontbk restarts automatically)
image: sequoiatools/cmd
entrypoint: sleep
command: "120"
wait: true
# Record timestamp after recovery
```

### Docker image conventions
- SSH/remote commands: `sequoiatools/cmd` (not `vijayviji/sshpass` — deprecated)
- KV load: `sequoiatools/gideon_latest`
- Collection load: `sequoiatools/magmaloader`
- CLI operations: `sequoiatools/couchbase-cli:7.6` (use `8.1` for cloud credential setup)
- PITR restore: `sequoiatools/pitr`

## PITR Restore Modes

| Mode | Behavior |
|------|----------|
| `random` | Select timestamps randomly |
| `sequential` | Restore in chronological order |
| `non-sequential` | Restore in random order (jumps back/forth) |
| `latest-n` | Select N most recent timestamps |
| `first-n` | Select N earliest timestamps |

## Chaos Test Matrix

| Scenario | Target | Recovery | Section |
|----------|--------|----------|---------|
| Kill memcached during rebalance | memcached | Retry rebalance | Both |
| Kill memcached randomly | memcached | Auto-restart | Single |
| Stop/start Couchbase service | couchbase-server | Manual restart | Both |
| Kill cbcontbk randomly | cbcontbk | Auto-restart | Single |
| Kill cbcontbk during rebalance out | cbcontbk | Wait for completion | Single |
| Kill cbcontbk during rebalance in | cbcontbk | Wait for completion | Single |
| Kill cbcontbk during failover | cbcontbk | Wait for completion | Single |
| Kill cbcontbk during recovery | cbcontbk | Wait for completion | Single |
| Kill cbcontbk before restore | cbcontbk | Wait + restore | Both |
| Kill cbcontbk after restore | cbcontbk | Wait | Both |
| Kill cbcontbk during restore | cbcontbk | `--resume` | Both |
| Kill cbcontbk during restore | cbcontbk | `--purge` | Both |
| Kill memcached during restore | memcached | `--resume` | Both |
| Stop Couchbase during backup | couchbase-server | Start + resume | Incremental |
| Kill memcached during backup | memcached | Resume | Incremental |
| Kill memcached during backup | memcached | Purge | Incremental |
| Kill cbbackupmgr during backup | cbbackupmgr | Resume | Incremental |

## Key Templates Reference

| Template | Purpose |
|----------|---------|
| `configure_backup_repo` | Initialize backup repository (NFS/local) |
| `configure_backup_repo_aws` | Initialize backup repository (S3) |
| `configure_backup_repo_azure` | Initialize backup repository (Azure) |
| `backup_cluster` | Take incremental/full backup |
| `resume_backup_cluster` | Resume failed backup |
| `purge_backup_cluster` | Purge failed backup state |
| `clean_backup_repo` | Delete backup repository |
| `rebalance_out` | Remove node (blocking) |
| `rebalance_out_wo_wait` | Remove node (non-blocking) |
| `rebalance_in` | Add node (blocking) |
| `rebalance_in_wo_wait` | Add node (non-blocking) |
| `rebalance` | Trigger rebalance |
| `wait_for_rebalance` | Wait for rebalance completion |
| `failover_node` | Graceful failover |
| `hard_failover_node` | Hard failover |
| `recover_node` | Recover failed node (`delta` or `full`) |
| `autofailover1Node` | Trigger auto-failover |
| `kill_process` | Kill named process on a node |
| `enable_autofailover` | Set auto-failover timeout |
| `create-multi-scopes-collections` | Create scope/collection hierarchy |

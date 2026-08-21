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
| `test_cont_backup_restore_gcp.yml` | Same test — GCP Cloud Storage |
| `scope_backup_restore_nfs.yml` | Scope for NFS test (magma storage) |
| `scope_backup_restore_cloud.yml` | Scope for S3/Azure/GCP tests (magma storage) |

Both scopes use magma-only bucket storage. `scope_backup_restore_nfs.yml` sets `continuous_backup_retention_period: 72` on all buckets.

## Storage Variant Differences

| Variant | Backup archive | Cont-backup location | Template suffix | Extra section |
|---------|---------------|----------------------|-----------------|---------------|
| NFS | `/mnt/nfs_data/test_system_backup` | `/mnt/nfs_data/test_system_continuous_backup` | _(none)_ | — |
| S3 | `s3://backup-restore-system-test/backups` | `s3://cont-bkp-system-test/systemtest/` | `_aws` | `setup_cloud_backup` |
| Azure | `az://backup-restore-system-test/backups` | `az://cont-bkp-system-test/systemtest/` | `_azure` | `setup_cloud_backup` |
| GCP | `gs://backup-restore-system-test/backups` | `gs://continuous-backup-system-test/systemtest/` | `_gcp` | `setup_cloud_backup` |

Cloud variants add a `setup_cloud_backup` section (before `initial_data_load`) that:
1. Disables auto-failover
2. Registers cloud credentials via the REST API
3. Enables continuous backup on each bucket with `continuousBackupEnabled=true` and a cloud credential ID
4. Re-enables auto-failover

**All backup templates in the `incremental_backup_pitr` section must use the cloud-specific suffix** (`_aws`, `_azure`, `_gcp`) — not the bare NFS templates. The final `clean_backup_repo` at the end of the file must also use the cloud variant.

When modifying one variant, apply the same change to others unless it is storage-specific.

### GCP credential registration

GCP uses service account JSON rather than access/secret key pairs. The `setup_cloud_backup` curl differs from S3/Azure:

```bash
source /etc/profile.d/gcp_credentials.sh
curl -X POST localhost:8091/settings/credentials/systemtest-gcp-id \
  -u Administrator:password \
  --json "$(jq -Rs '{type:"gcp",fields:{jsonCredentials:.,region:"us"}}' $GOOGLE_APPLICATION_CREDENTIALS)"
```

`$GOOGLE_APPLICATION_CREDENTIALS` is set by `gcp_credentials.sh` and points to the service account key JSON file on the SSH host. The `jq` command reads and embeds the file contents as the `jsonCredentials` field.

## Test Sections

NFS has 3 sections; S3/Azure have 4 (they prepend `setup_cloud_backup`):

1. **`setup_cloud_backup`** _(cloud variants only)_ — Register cloud credentials, enable continuous backup per bucket.
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
# Cloud variants add: --storage-type aws|azure|gcp --obj-staging-dir /data/s3|/data/azure|/data/gcp
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

### Magmaloader key ranges
Each test section uses a non-overlapping `--start` offset so doc keys never collide across sections (e.g., 0→25M in `initial_data_load`, 25M→30M in `single_backup_pitr`, 30M→35M in `incremental_backup_pitr`). When adding a new section, continue from the previous section's end range rather than restarting from 0.

### Docker image conventions
- SSH/remote commands: `sequoiatools/cmd` (not `vijayviji/sshpass` — deprecated)
- KV load: `sequoiatools/gideon_latest`
- Collection load: `sequoiatools/magmaloader`
- CLI operations: `sequoiatools/couchbase-cli:8.5`
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
| `configure_backup_repo_gcp` | Initialize backup repository (GCP) |
| `backup_cluster` | Take incremental/full backup (NFS/local) |
| `backup_cluster_aws` | Take incremental/full backup (S3) |
| `backup_cluster_azure` | Take incremental/full backup (Azure) |
| `backup_cluster_gcp` | Take incremental/full backup (GCP) |
| `resume_backup_cluster` | Resume failed backup (NFS/local) |
| `resume_backup_cluster_aws` | Resume failed backup (S3) |
| `resume_backup_cluster_azure` | Resume failed backup (Azure) |
| `resume_backup_cluster_gcp` | Resume failed backup (GCP) |
| `purge_backup_cluster` | Purge failed backup state (NFS/local) |
| `purge_backup_cluster_aws` | Purge failed backup state (S3) |
| `purge_backup_cluster_azure` | Purge failed backup state (Azure) |
| `purge_backup_cluster_gcp` | Purge failed backup state (GCP) |
| `clean_backup_repo` | Delete backup repository (NFS/local) |
| `clean_backup_repo_aws` | Delete backup repository (S3) |
| `clean_backup_repo_azure` | Delete backup repository (Azure) |
| `clean_backup_repo_gcp` | Delete backup repository (GCP) |
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

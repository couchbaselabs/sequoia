#!/usr/bin/env python3
import argparse
import random
import sys
import os
import paramiko

REMOTE_TIMESTAMP_FILE = "/tmp/timestamps.txt"


def read_timestamps_from_remote(ssh_host, ssh_user, ssh_password):
    """Read timestamps from remote host via SSH."""
    timestamps = []
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ssh_host, username=ssh_user, password=ssh_password)

        stdin, stdout, stderr = client.exec_command(f"cat {REMOTE_TIMESTAMP_FILE}")
        exit_status = stdout.channel.recv_exit_status()

        if exit_status != 0:
            stderr_str = stderr.read().decode('utf-8')
            print(f"Error reading timestamp file from {ssh_host}: {stderr_str}", file=sys.stderr)
            client.close()
            sys.exit(1)

        for line in stdout.read().decode('utf-8').splitlines():
            line = line.strip()
            if line:
                timestamps.append(line)

        client.close()
        return timestamps

    except Exception as e:
        print(f"SSH connection error while reading timestamps: {str(e)}", file=sys.stderr)
        sys.exit(1)


def get_timestamps_by_mode(timestamps, n, mode):
    """Return n timestamps based on the selection mode."""
    if n > len(timestamps):
        print(f"Warning: Requested {n} timestamps but only {len(timestamps)} available", file=sys.stderr)
        n = len(timestamps)

    if mode == "random":
        selected = random.sample(timestamps, n)
        random.shuffle(selected)
        return selected
    elif mode == "sequential":
        selected = random.sample(timestamps, n)
        return sorted(selected)
    elif mode == "non-sequential":
        selected = random.sample(timestamps, n)
        return sorted(selected, reverse=True)
    elif mode == "latest-n":
        sorted_ts = sorted(timestamps, reverse=True)
        return sorted_ts[:n]
    elif mode == "first-n":
        sorted_ts = sorted(timestamps)
        return sorted_ts[:n]
    else:
        print(f"Error: Unknown mode '{mode}'", file=sys.stderr)
        sys.exit(1)


def run_pitr(ssh_host, ssh_user, ssh_password, cluster_ip, rest_user, rest_password,
             archive_path, repo_name, cont_backup_location, timestamp, threads=8, tmp_dir="/data/tmp",
             resume=False, purge=False, storage_type="nfs", obj_staging_dir=None):
    """Run PITR restore command on remote host via SSH using paramiko."""
    cmd = (
        f"/opt/couchbase/bin/cbcontbk restore "
        f"-a {archive_path} -r {repo_name} "
        f"-c {cluster_ip}:8091 -u {rest_user} -p {rest_password} -t {threads} "
        f"-l {cont_backup_location} -d {tmp_dir} "
        f"-T {timestamp}"
    )
    if resume:
        cmd += " --resume"
    if purge:
        cmd += " --purge"

    if storage_type == "aws":
        cmd += (
            f" --obj-staging-dir {obj_staging_dir}"
            f" --obj-region us-east-1"
            f" --obj-access-key-id $AWS_ACCESS_KEY_ID"
            f" --obj-secret-access-key $AWS_SECRET_ACCESS_KEY"
        )
        cmd = f"source /etc/profile.d/s3_credentials.sh; {cmd}"
    elif storage_type == "azure":
        cmd += (
            f" --obj-staging-dir {obj_staging_dir}"
            f" --obj-region westus"
            f" --obj-endpoint $AZURE_STORAGE_ENDPOINT"
            f" --obj-access-key-id $AZURE_STORAGE_ACCOUNT"
            f" --obj-secret-access-key $AZURE_STORAGE_KEY"
        )
        cmd = f"source /etc/profile.d/azure_credentials.sh; {cmd}"
    elif storage_type == "gcp":
        cmd += f" --obj-staging-dir {obj_staging_dir}"

    print(f"Running PITR restore to timestamp: {timestamp}\n cmd: {cmd}\n")

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ssh_host, username=ssh_user, password=ssh_password)

        stdin, stdout, stderr = client.exec_command(cmd)
        exit_status = stdout.channel.recv_exit_status()

        stdout_str = stdout.read().decode('utf-8')
        stderr_str = stderr.read().decode('utf-8')

        client.close()

        if exit_status != 0:
            print(f"Error running PITR for timestamp {timestamp}: {stdout_str} : {stderr_str}", file=sys.stderr)
            return False

        print(f"PITR restore completed for timestamp: {timestamp}")
        print(stdout_str)
        return True

    except Exception as e:
        print(f"SSH connection error for timestamp {timestamp}: {str(e)}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description='Point in time recovery to n timestamps')
    parser.add_argument('--num_timestamps', type=int, help='Number of timestamps to recover to')
    parser.add_argument('--mode', choices=['random', 'sequential', 'non-sequential', 'latest-n', 'first-n'],
                        default='random', help='Timestamp selection mode: random (n random), '
                        'sequential (n random sorted ascending), non-sequential (n random sorted descending), '
                        'latest-n (n most recent descending), first-n (n earliest ascending)')
    parser.add_argument('--ssh-host', required=True, help='SSH host IP to run cbcontbk on')
    parser.add_argument('--ssh-user', required=True, help='SSH username')
    parser.add_argument('--ssh-password', required=True, help='SSH password')
    parser.add_argument('--cluster-ip', required=True, help='Couchbase cluster IP')
    parser.add_argument('--rest-user', required=True, help='Couchbase REST username')
    parser.add_argument('--rest-password', required=True, help='Couchbase REST password')
    parser.add_argument('--archive', required=True, help='Backup archive path (-a)')
    parser.add_argument('--repo', required=True, help='Backup repo name (-r)')
    parser.add_argument('--cont-backup-location', required=True, help='Continuous backup location (-l)')
    parser.add_argument('--threads', type=int, default=8, help='Number of threads (-t)')
    parser.add_argument('--tmp-dir', default='/data/tmp', help='Temporary directory (-d)')
    parser.add_argument('--resume', action='store_true', help='Resume a previous restore operation')
    parser.add_argument('--purge', action='store_true', help='Purge a previous failed restore operation')
    parser.add_argument('--storage-type', choices=['nfs', 'aws', 'azure', 'gcp'],
                        default='nfs', help='Storage type for backup archive (default: nfs)')
    parser.add_argument('--obj-staging-dir', help='Object staging directory (required for aws, azure, gcp)')

    args = parser.parse_args()

    if args.storage_type in ['aws', 'azure', 'gcp'] and not args.obj_staging_dir:
        print(f"Error: --obj-staging-dir is required when storage-type is {args.storage_type}", file=sys.stderr)
        sys.exit(1)

    if args.num_timestamps <= 0:
        print("Error: num_timestamps must be a positive integer", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching timestamps from {args.ssh_host}:{REMOTE_TIMESTAMP_FILE}")
    timestamps = read_timestamps_from_remote(args.ssh_host, args.ssh_user, args.ssh_password)
    if not timestamps:
        print("Error: No timestamps found in file", file=sys.stderr)
        sys.exit(1)

    selected_ts = get_timestamps_by_mode(timestamps, args.num_timestamps, args.mode)
    print(f"Selected {len(selected_ts)} timestamps for PITR (mode: {args.mode}):")
    for ts in selected_ts:
        print(f"  {ts}")

    for i, ts in enumerate(selected_ts, 1):
        print(f"\n[{i}/{len(selected_ts)}] Running PITR for timestamp: {ts}")
        if not run_pitr(
            args.ssh_host, args.ssh_user, args.ssh_password,
            args.cluster_ip, args.rest_user, args.rest_password,
            args.archive, args.repo, args.cont_backup_location,
            ts, args.threads, args.tmp_dir,
            args.resume, args.purge, args.storage_type, args.obj_staging_dir
        ):
            print(f"Error: PITR failed for timestamp {ts}. Exiting.", file=sys.stderr)
            sys.exit(1)

    print(f"\nPITR completed successfully for all {len(selected_ts)} timestamps")


if __name__ == "__main__":
    main()

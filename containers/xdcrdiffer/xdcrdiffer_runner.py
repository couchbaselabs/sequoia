#!/usr/bin/env python3
"""Sequoia ActionSpec wrapper around Couchbase's shipped xdcrDiffer tooling.

Invocation is delegated to /opt/couchbase/bin/runDiffer.sh (the official wrapper
that ships on the server image), so the flag assembly, cbauth setup and output
layout always match the differ version on the node. This script adds only the
piece runDiffer.sh does not provide: a pass/fail decision. The key gate is
--strict-no-diff, which parses the per-collection mutationDiff output to confirm
zero divergence (xdcrDiffer compares key-by-key within each collection, so this
catches collection-level imbalances the aggregate bucket-count check misses).

The normal/strict path uses runDiffer.sh -y <yaml>, so the DCP/worker tuning in
the generated config is preserved (matters at 10K collections). Encryption
(--passphrase) cannot be combined with -y (runDiffer.sh rejects it), so it falls
back to cmdline mode with -x, driving the passphrase prompt over a PTY since
golang.org/x/term requires a real TTY. Decrypt mode calls the xdcrDiffer binary
directly (runDiffer.sh has no decrypt path).
"""
import argparse
import json
import os
import pty
import select
import shlex
import shutil
import subprocess
import sys
import time

import yaml

RUNDIFFER = "/opt/couchbase/bin/runDiffer.sh"
XDCR_DIFFER_BIN = "/opt/couchbase/bin/xdcrDiffer"
MAGIC_BYTES = b"Couchbase Encrypted"
YAML_CONFIG_PATH = "/tmp/xdcr_differ_params.yaml"

# Diff-category keys inside mutationDiffDetails / mutationBodyDiffDetails JSON.
DIFF_DETAIL_CATEGORIES = ("Mismatch", "MissingFromSource", "MissingFromTarget")


def parse_args(argv):
    p = argparse.ArgumentParser(description="xdcrDiffer runner (via runDiffer.sh)")
    p.add_argument("--source-host", default="")
    p.add_argument("--source-port", default="8091")
    p.add_argument("--source-username", default="Administrator")
    p.add_argument("--source-password", default="password")
    p.add_argument("--source-bucket", default="default")
    p.add_argument("--target-bucket", default="default")
    # runDiffer.sh resolves the target cluster through the source cluster's
    # remote-cluster reference (metakv), so no target host/creds are needed.
    p.add_argument("--remote-cluster-name", default="remote")
    p.add_argument("--compare-type", choices=["body", "meta", "both"], default="body")
    p.add_argument("--num-bins", type=int, default=5)
    p.add_argument("--output-dir", default="/tmp/xdcr_differ_outputs")
    p.add_argument("--passphrase", default="")
    p.add_argument("--decrypt-mode", action="store_true")
    p.add_argument("--decrypt-file", default="")
    p.add_argument("--extra-flags", default="")
    p.add_argument("--verify-enc-suffix", action="store_true",
                   help="Assert outputDir contains at least one .enc file.")
    p.add_argument("--verify-magic-bytes", action="store_true",
                   help="Assert an .enc file starts with the Couchbase Encrypted magic bytes.")
    p.add_argument("--verify-no-enc-files", action="store_true",
                   help="Assert outputDir contains zero .enc files (non-encrypted regression).")
    p.add_argument("--strict-no-diff", action="store_true",
                   help="Fail if any collection's mutationDiff output reports divergence.")
    p.add_argument("--expect-fail", action="store_true",
                   help="Invert exit code — succeed if the differ exits non-zero.")
    p.add_argument("--verbose", action="store_true",
                   help="Echo the differ's full stdout even on success (default: "
                        "suppressed; only the one-line OK/FAIL gate is printed).")
    p.add_argument("--retries", type=int, default=2,
                   help="With --strict-no-diff, if the mutationDiff is non-empty, "
                        "re-run the differ this many additional times before failing. "
                        "An in-flight mutation clears on a re-run once replication "
                        "drains; a genuine replication loss persists across every "
                        "attempt. 0 disables retrying (fail on first non-empty diff).")
    p.add_argument("--retry-wait", type=int, default=60,
                   help="Seconds to wait between --strict-no-diff retries so the last "
                        "in-flight mutations can finish replicating before re-checking.")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--keep-output", action="store_true")
    p.add_argument("--timeout", type=int, default=1200)
    return p.parse_args(argv)


def build_yaml_config(args):
    out = args.output_dir
    cfg = {
        "sourceUrl": f"{args.source_host}:{args.source_port}",
        "sourceUsername": args.source_username,
        "sourcePassword": args.source_password,
        "sourceBucketName": args.source_bucket,
        # Target cluster is resolved through the source cluster's remote-cluster
        # reference (metakv); no target host/creds needed.
        "remoteClusterName": args.remote_cluster_name,
        "targetBucketName": args.target_bucket,
        "outputFileDir": out,
        "sourceFileDir": f"{out}/source",
        "targetFileDir": f"{out}/target",
        "checkpointFileDir": f"{out}/checkpoint",
        "fileDifferDir": f"{out}/fileDiff",
        "mutationDifferDir": f"{out}/mutationDiff",
        "newCheckpointFileName": "checkpoint_test.json",
        "checkpointInterval": 600,
        "completeBySeqno": True,
        "compareType": args.compare_type,
        "runDataGeneration": True,
        "runFileDiffer": True,
        "runMutationDiffer": True,
        "numberOfSourceDcpClients": 1,
        "numberOfWorkersPerSourceDcpClient": 64,
        "numberOfTargetDcpClients": 1,
        "numberOfWorkersPerTargetDcpClient": 64,
        "numberOfWorkersForFileDiffer": 30,
        "numberOfWorkersForMutationDiffer": 30,
        "numberOfBins": args.num_bins,
        "numberOfFileDesc": 500,
        "mutationDifferBatchSize": 100,
        "mutationDifferTimeout": 30,
        "bucketOpTimeout": 60,
        "clearBeforeRun": "false" if args.keep_output else "true",
    }
    with open(YAML_CONFIG_PATH, "w") as f:
        yaml.safe_dump(cfg, f)
    return cfg


def build_run_cmd(args):
    """Pick the runDiffer.sh invocation. YAML mode preserves the worker tuning,
    but runDiffer.sh forbids -y with encryption, so passphrase runs use cmdline."""
    if args.passphrase:
        parts = [
            RUNDIFFER,
            "-h", f"{args.source_host}:{args.source_port}",
            "-u", args.source_username,
            "-p", args.source_password,
            "-s", args.source_bucket,
            "-t", args.target_bucket,
            "-r", args.remote_cluster_name,
            "-o", args.output_dir,
            "-m", args.compare_type,
            "-x",  # encryption mode (interactive passphrase prompt)
        ]
        if not args.keep_output:
            parts.append("-c")
    else:
        build_yaml_config(args)
        parts = [RUNDIFFER, "-y", YAML_CONFIG_PATH]
    if args.extra_flags:
        parts.extend(shlex.split(args.extra_flags))
    return parts


def build_decrypt_cmd(args):
    parts = [XDCR_DIFFER_BIN, "-decrypt"]
    if args.decrypt_file:
        parts.append(args.decrypt_file)
    if args.passphrase:
        parts.append("-encryptionPassphrase")
    if args.extra_flags:
        parts.extend(shlex.split(args.extra_flags))
    return parts


def run_plain(cmd, timeout, quiet=True):
    """Run the differ, capturing its (very verbose) stdout/stderr.

    On a clean run the differ prints per-vbucket DCP/dump progress and count
    tables that clutter the console; with `quiet` we swallow that and let the
    pass/fail decision come from the runner's own one-line OK/FAIL. The captured
    output is still surfaced when the differ exits non-zero so failures remain
    debuggable.
    """
    try:
        proc = subprocess.run(
            cmd, timeout=timeout,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        if proc.returncode != 0 or not quiet:
            sys.stdout.write(proc.stdout or "")
        return proc.returncode
    except subprocess.TimeoutExpired as e:
        sys.stderr.write(f"timeout after {timeout}s: {e}\n")
        return 124


def run_with_passphrase(cmd, passphrase, timeout):
    """Drive the differ under a PTY so golang.org/x/term gets a real TTY."""
    prompts = [
        b"enter encryption passphrase",
        b"enter the same encryption passphrase again",
    ]
    pid, fd = pty.fork()
    if pid == 0:
        os.execvpe(cmd[0], cmd, os.environ.copy())
    deadline = time.time() + timeout
    buf = b""
    sent = 0
    try:
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                os.kill(pid, 9)
                sys.stderr.write(f"timeout after {timeout}s\n")
                return 124
            r, _, _ = select.select([fd], [], [], min(1.0, remaining))
            if fd in r:
                try:
                    chunk = os.read(fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
                if sent < len(prompts) and prompts[sent].lower() in buf.lower():
                    os.write(fd, passphrase.encode() + b"\n")
                    sent += 1
                    buf = b""
            pid_done, status = os.waitpid(pid, os.WNOHANG)
            if pid_done == pid:
                return os.waitstatus_to_exitcode(status)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
    _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status)


def find_enc_files(root):
    matches = []
    for dirpath, _, files in os.walk(root):
        for name in files:
            if name.endswith(".enc"):
                matches.append(os.path.join(dirpath, name))
    return matches


def verify_magic_bytes(path):
    with open(path, "rb") as f:
        head = f.read(64)
    return MAGIC_BYTES in head


def _load_json(path):
    try:
        with open(path) as f:
            text = f.read().strip()
    except OSError:
        return None
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _sample_keys(entries, limit=10):
    """Best-effort list of doc keys from a mutationDiff category value.

    The category value is usually a dict keyed by docId (or a list of docIds);
    fall back to the stringified value for anything else so the FAIL line always
    names the offending docs instead of just a count.
    """
    if isinstance(entries, dict):
        keys = list(entries.keys())
    elif isinstance(entries, list):
        keys = [k if isinstance(k, (str, int)) else json.dumps(k) for k in entries]
    else:
        return len(entries) if hasattr(entries, "__len__") else 1, str(entries)
    sample = ", ".join(str(k) for k in keys[:limit])
    more = "" if len(keys) <= limit else f", +{len(keys) - limit} more"
    return len(keys), f"{sample}{more}"


def verify_strict_no_diff(mutation_dir):
    """Per-collection divergence check.

    xdcrDiffer's mutationDiffer ALWAYS writes its output files even on a clean
    run (e.g. {"Mismatch":{},"MissingFromSource":{},"MissingFromTarget":{}} and
    []), so a file-size heuristic false-fails on perfect replication. Parse the
    JSON instead: detail files (dicts) must have empty diff categories and key
    files (arrays) must be empty. The mutationDiff output is authoritative — it
    re-verifies the fileDiffer's candidate diffs, so transient DCP-snapshot
    diffs that already converged do not count.

    On failure the actual offending doc keys are included in the message (not
    just a count), so the one-line FAIL is enough to identify the doc — no need
    to keep/inspect the output dir of an otherwise-ephemeral container.
    """
    if not os.path.isdir(mutation_dir):
        return True, "no mutationDiff dir"
    problems = []
    for dirpath, _, files in os.walk(mutation_dir):
        for name in files:
            if name.endswith(".enc"):
                continue
            data = _load_json(os.path.join(dirpath, name))
            if data is None:
                continue
            if isinstance(data, dict):
                for category in DIFF_DETAIL_CATEGORIES:
                    entries = data.get(category)
                    if entries:
                        count, keys = _sample_keys(entries)
                        problems.append(f"{name}: {category}={count} keys=[{keys}]")
            elif isinstance(data, list):
                if data:
                    count, keys = _sample_keys(data)
                    problems.append(f"{name}: {count} keys=[{keys}]")
            else:
                problems.append(f"{name}: unexpected non-JSON content")
    if problems:
        return False, "; ".join(problems)
    return True, "no diffs"


def dump_mutation_diff_details(mutation_dir):
    """Dump the full mutationDiff file contents after retries are exhausted.

    The one-line FAIL message names the offending doc keys (e.g. keys=[9]) but
    not which scope/collection they live in. xdcrDiffer encodes the collection
    in the mutationDiff file *name* (and, for detail files, in the body), so on
    a terminal failure we print every non-empty file verbatim. That reveals
    whether the offending doc sits in a real user collection (a genuine
    replication loss) or in the `_system` scope (a false positive: XDCR's
    filterSystemScope=true legitimately does not replicate `_system`, yet the
    differ still compares it). Without this an ephemeral container is gone
    before anyone can inspect the dir.
    """
    if not os.path.isdir(mutation_dir):
        print(f"[xdcrdiffer-runner] (no mutationDiff dir at {mutation_dir} to dump)")
        return
    print(f"[xdcrdiffer-runner] ===== mutationDiff details dump ({mutation_dir}) =====")
    dumped = False
    for dirpath, _, files in os.walk(mutation_dir):
        for name in sorted(files):
            if name.endswith(".enc"):
                continue
            full = os.path.join(dirpath, name)
            data = _load_json(full)
            # Skip files that are clean (empty categories / empty list) so the
            # dump only surfaces the actual divergence.
            if isinstance(data, dict):
                if not any(data.get(c) for c in DIFF_DETAIL_CATEGORIES):
                    continue
            elif isinstance(data, list):
                if not data:
                    continue
            rel = os.path.relpath(full, mutation_dir)
            print(f"[xdcrdiffer-runner] --- {rel} ---")
            if isinstance(data, (dict, list)):
                print(json.dumps(data, indent=2, sort_keys=True))
            else:
                print(str(data))
            dumped = True
    if not dumped:
        print("[xdcrdiffer-runner] (no non-empty mutationDiff files found)")
    print("[xdcrdiffer-runner] ===== end mutationDiff details dump =====")


def main(argv):
    args = parse_args(argv)
    cmd = build_decrypt_cmd(args) if args.decrypt_mode else build_run_cmd(args)

    print(f"[xdcrdiffer-runner] cmd: {' '.join(shlex.quote(c) for c in cmd)}")
    if not args.decrypt_mode and not args.passphrase and os.path.exists(YAML_CONFIG_PATH):
        print(f"[xdcrdiffer-runner] yaml: {YAML_CONFIG_PATH}")
        if args.dry_run:
            with open(YAML_CONFIG_PATH) as f:
                sys.stdout.write(f.read())
    if args.dry_run:
        return 0

    out = args.output_dir
    # Retrying only makes sense for the strict no-diff gate: a non-empty
    # mutationDiff is either a real replication loss (persists) or an in-flight
    # mutation (clears once replication drains). Every other mode is a single run.
    attempts = (1 + max(0, args.retries)) if args.strict_no_diff else 1

    for attempt in range(1, attempts + 1):
        if args.passphrase:
            rc = run_with_passphrase(cmd, args.passphrase, args.timeout)
        else:
            rc = run_plain(cmd, args.timeout, quiet=not args.verbose)

        suffix = f" (attempt {attempt}/{attempts})" if attempts > 1 else ""
        print(f"[xdcrdiffer-runner] differ exit: {rc}{suffix}")

        if args.expect_fail:
            if rc == 0:
                print("[xdcrdiffer-runner] FAIL: expected non-zero exit, got 0")
                return 1
            print("[xdcrdiffer-runner] OK: differ failed as expected")
            return 0

        if rc != 0:
            return rc

        if not args.decrypt_mode:
            for sub in ("", "/source", "/target", "/checkpoint", "/fileDiff", "/mutationDiff"):
                path = out + sub
                if not os.path.isdir(path):
                    print(f"[xdcrdiffer-runner] FAIL: missing directory {path}")
                    return 2

        enc_files = find_enc_files(out)
        if args.verify_enc_suffix:
            if not enc_files:
                print(f"[xdcrdiffer-runner] FAIL: no .enc files under {out}")
                return 2
            print(f"[xdcrdiffer-runner] OK: {len(enc_files)} .enc files found")

        if args.verify_no_enc_files and enc_files:
            print(f"[xdcrdiffer-runner] FAIL: {len(enc_files)} .enc files present in non-encrypted run")
            return 2

        if args.verify_magic_bytes:
            if not enc_files:
                print("[xdcrdiffer-runner] FAIL: no .enc files to inspect for magic bytes")
                return 2
            if not any(verify_magic_bytes(p) for p in enc_files):
                print(f"[xdcrdiffer-runner] FAIL: magic bytes {MAGIC_BYTES!r} not found in any .enc file")
                return 2
            print("[xdcrdiffer-runner] OK: magic bytes verified")

        if not args.strict_no_diff:
            break

        # Authoritative gate. The mutationDiffer re-fetches each candidate key
        # directly on both clusters, so orphan tombstones (deleted on source,
        # never materialized on target) already cancel out and never land here.
        # A non-empty result is therefore either a genuine replication loss or a
        # still-in-flight mutation; we tell them apart by re-running after a drain
        # wait (clearBeforeRun re-dumps both clusters fresh): an in-flight key
        # disappears on the next attempt, a real loss persists across all of them.
        ok, msg = verify_strict_no_diff(f"{out}/mutationDiff")
        if ok:
            print(f"[xdcrdiffer-runner] OK: {msg}")
            break
        if attempt < attempts:
            print(f"[xdcrdiffer-runner] diffs on attempt {attempt}/{attempts}: {msg}")
            print(f"[xdcrdiffer-runner] re-running after {args.retry_wait}s drain "
                  "(in-flight mutations clear on retry; real replication losses persist)")
            time.sleep(args.retry_wait)
            continue
        print(f"[xdcrdiffer-runner] FAIL: diffs persisted across {attempts} attempt(s): {msg}")
        dump_mutation_diff_details(f"{out}/mutationDiff")
        return 2

    if not args.keep_output and not args.decrypt_mode:
        shutil.rmtree(out, ignore_errors=True)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

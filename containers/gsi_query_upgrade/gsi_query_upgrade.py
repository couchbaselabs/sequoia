#!/usr/bin/env python3
"""
GSI/Query upgrade test tool (tests/upgrade/gsi_query). REST only, so it works against any server version.

Pre-upgrade (-version <initial>):
  wait_for_docs             wait until every loaded collection has its expected doc count and the count is stable
  apply_index_spec          create the indexes in index_spec.yml the cluster version supports, build them in
                            stages of at most --max_concurrent_builds instances, wait online
  disable_sequential_scans  set the sequential-scan bit (0x4000) in queryN1QLFeatCtrl (7.6+)
  update_statistics         UPDATE STATISTICS on every keyspace in the spec, empty collections included
  create_udfs               fixed SQL++ (scoped) and JavaScript (global) UDFs used by the query suite
  capture_baseline          EXPLAIN summary, row count, latency, result hash and named PREPARE per suite query

Post-upgrade (-version <final> -skip_setup):
  wait_for_indexes          every index instance Ready again (indexer warmup after an in-place offline upgrade)
  validate_statistics       stats survived, every keyspace answers, UPDATE STATISTICS still completes
  validate_baseline         plan diff, result diff on every query node, prepared survival + re-EXECUTE, UDFs,
                            settings, QUERY_METADATA, smoke run of queries the initial version could not run
  apply_index_spec          adds the indexes the final version newly supports
  run_suite / suite_report  loop the suite under writes + rebalances; static results must keep matching
  plasma_scans / capture_plasma_state / validate_plasma   holes in plasma pages made before the upgrade (CBSE-23065), judged
                            after it from the files indexmanager report_storage_stats wrote
  capture_bhive_state / validate_bhive / compare_recall   Magma-backed BHIVE indexes churned before the upgrade, recall readings
                            (the load, churn, writes and stats reading are indexmanager actions)
  run_ddl / ddl_report      offline upgrade only: create/build/query/drop a throwaway index while the cluster is
                            mixed-version (DDL is not allowed during a rebalance)
  rebalance_in / rebalance_out   topology changes on the upgraded cluster

Exits non-zero when a check fails.
"""
import argparse
import hashlib
import json
import logging
import os
import re
import statistics
import sys
import time
from datetime import datetime, timedelta

import requests
import urllib3
import yaml

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SEQSCAN_BIT = 0x4000
JOIN_OPS = {"NestedLoopJoin", "HashJoin", "Join", "IndexJoin", "Nest", "NestedLoopNest", "HashNest",
            "IndexNest", "Unnest"}
MULTI_SCAN_OPS = {"IntersectScan", "UnionScan", "OrderedIntersectScan", "DistinctScan", "ExpressionScan"}
PLACEHOLDER_RE = re.compile(r"\{([a-z0-9_]+)(?:\.([a-z0-9_]+))?\}")
UDF_JS_LIBRARY = "upq_lib"
UDF_JS_CODE = "function upq_concat(a, b) { return a + '|' + b; }"
UDF_STATEMENTS = [
    'CREATE OR REPLACE FUNCTION upq_label(a, b) LANGUAGE JAVASCRIPT AS "upq_concat" AT "upq_lib"',
    'CREATE OR REPLACE FUNCTION default:hotel_static.hs1.upq_price_band(p) { CASE WHEN p IS NULL THEN "none" '
    'WHEN p < 500 THEN "low" WHEN p < 2000 THEN "mid" ELSE "high" END }',
]
UDF_NAMES = ["upq_label", "upq_price_band"]

log = logging.getLogger("gsi_query_upgrade")


def version_float(version):
    """'8.0.1-1234-enterprise' -> 8.0"""
    match = re.match(r"(\d+)\.(\d+)", version or "")
    return float(f"{match.group(1)}.{match.group(2)}") if match else 0.0


def keyspace_path(keyspace):
    """'hotel_static.hs1.c1' -> '`hotel_static`.`hs1`.`c1`'"""
    return ".".join(f"`{part}`" for part in keyspace.split("."))


def summarize_plan(plan):
    """Reduce an EXPLAIN plan to what a regression changes: index/scan choice, join method and order,
    covering vs fetch, sort, and whether CBO costed the plan."""
    scans, joins = [], []
    counters = {"fetch": 0, "order": 0, "cbo": False}

    def walk(node):
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        op = node.get("#operator")
        if op:
            if "Scan" in op and op not in MULTI_SCAN_OPS:
                ks = node.get("keyspace") or node.get("as") or ""
                covered = ":covered" if node.get("covers") else ""
                scans.append(f"{op}:{ks}:{node.get('index', '')}{covered}")
            elif op in MULTI_SCAN_OPS:
                scans.append(op)
            elif op in JOIN_OPS:
                joins.append(f"{op}:{node.get('alias') or node.get('as') or node.get('keyspace') or ''}")
            elif op == "Fetch":
                counters["fetch"] += 1
            elif op in ("Order", "Sort"):
                counters["order"] += 1
        estimates = node.get("optimizer_estimates")
        if isinstance(estimates, dict) and estimates.get("cost", -1) > 0:
            counters["cbo"] = True
        for value in node.values():
            walk(value)

    walk(plan)
    return {"scans": sorted(scans), "joins": joins, "fetch": counters["fetch"],
            "order": counters["order"], "cbo": counters["cbo"]}


def diff_plans(before, after):
    return [f"{key}: {before.get(key)} -> {after.get(key)}"
            for key in ("scans", "joins", "fetch", "order", "cbo") if before.get(key) != after.get(key)]


# {index template: the template standing for its group}, from index_spec.yml equivalent_indexes; set by validate_baseline
EQUIVALENT_INDEXES = {}


def equivalence_map(spec):
    mapping = {}
    for group in spec.get("equivalent_indexes") or []:
        for template in group[1:]:
            mapping[template] = group[0]
    return mapping


def canonical_plan(plan):
    """The plan with every scan on an index of an equivalence group named after the group's first template. Only the index
    name changes: the scan operator, the keyspace and the covered flag stay, so a swap that stops covering still differs."""
    if not EQUIVALENT_INDEXES or not plan:
        return plan
    scans = []
    for scan in plan.get("scans", []):
        parts = scan.split(":")             # operator : keyspace : index [: covered]
        if len(parts) >= 3:
            template, _, suffix = parts[2].partition("_")
            if template in EQUIVALENT_INDEXES:
                parts[2] = EQUIVALENT_INDEXES[template] + ("_" + suffix if suffix else "")
        scans.append(":".join(parts))
    return {**plan, "scans": sorted(scans)}


def only_equivalent_index_swaps(before, after):
    """True when the plans differ, but not once equivalent indexes are treated as one."""
    return bool(diff_plans(before, after)) and not diff_plans(canonical_plan(before), canonical_plan(after))


def cbo_only(changes):
    """Only whether CBO costed the plan differs: same indexes, joins, fetch and sort (a version that starts costing
    a plan shape it did not before), so a warning rather than a regression."""
    return bool(changes) and all(c.startswith("cbo:") for c in changes)


def result_hash(rows, ordered):
    canon = [json.dumps(r, sort_keys=True, separators=(",", ":")) for r in rows]
    if not ordered:
        canon.sort()
    return hashlib.sha256("\n".join(canon).encode()).hexdigest()


def print_table(header, rows):
    widths = [max(len(str(x)) for x in col) for col in zip(header, *rows)] if rows else [len(h) for h in header]
    line = "  ".join(f"{{:<{w}}}" for w in widths)
    out = [line.format(*header), line.format(*["-" * w for w in widths])]
    out += [line.format(*[str(c) for c in row]) for row in rows]
    log.info("\n" + "\n".join(out))


class Checks:
    """Collects failures and warnings; report() raises if anything failed."""

    def __init__(self, action):
        self.action, self.failures, self.warnings = action, [], []

    def fail(self, msg):
        self.failures.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    def report(self):
        for w in self.warnings:
            log.warning(f"[{self.action}] {w}")
        for f in self.failures:
            log.error(f"[{self.action}] {f}")
        if self.failures:
            raise SystemExit(f"{self.action}: {len(self.failures)} failure(s)")
        log.info(f"[{self.action}] passed with {len(self.warnings)} warning(s)")


class Cluster:
    def __init__(self, host, username, password, tls=False):
        self.host = host.split(":")[0]
        self.auth = (username, password)
        self.username, self.password = username, password
        self.scheme = "https" if tls else "http"
        self.mgmt_port = 18091 if tls else 8091
        self.query_port = 18093 if tls else 8093

    # -------------------------------------------------------------- REST

    def mgmt(self, method, path, host=None, **kwargs):
        url = f"{self.scheme}://{host or self.host}:{self.mgmt_port}{path}"
        return requests.request(method, url, auth=self.auth, timeout=120, verify=False, **kwargs)

    def query(self, statement, host=None, timeout=300, params=None):
        """Returns (ok, rows, body, elapsed_seconds)."""
        url = f"{self.scheme}://{host or self.host}:{self.query_port}/query/service"
        payload = {"statement": statement, "timeout": f"{timeout}s", "scan_consistency": "request_plus"}
        payload.update(params or {})
        start = time.perf_counter()
        try:
            response = requests.post(url, json=payload, auth=self.auth, timeout=timeout + 60, verify=False)
            body = response.json()
        except (requests.exceptions.RequestException, ValueError) as e:
            return False, [], {"errors": [{"msg": str(e)}]}, time.perf_counter() - start
        ok = response.status_code == 200 and body.get("status") == "success"
        return ok, body.get("results", []), body, time.perf_counter() - start

    @staticmethod
    def errors(body):
        return " | ".join(str(e.get("msg")) for e in (body or {}).get("errors", []))

    @staticmethod
    def error_codes(body):
        return {e.get("code") for e in (body or {}).get("errors", [])}

    # -------------------------------------------------------------- cluster info

    def nodes(self):
        response = self.mgmt("GET", "/pools/default")
        response.raise_for_status()
        return response.json().get("nodes", [])

    def versions(self):
        return sorted({n.get("version", "") for n in self.nodes()})

    def min_version(self):
        return min(version_float(v) for v in self.versions())

    def query_nodes(self):
        return [n["hostname"].rsplit(":", 1)[0].strip("[]") for n in self.nodes()
                if "n1ql" in n.get("services", []) and n.get("clusterMembership") == "active"] or [self.host]

    def index_states(self, host=None):
        """{(bucket, scope, collection, name): state} for all GSI indexes."""
        ok, rows, body, _ = self.query('SELECT i.name, i.bucket_id, i.scope_id, i.keyspace_id, i.state '
                                       'FROM system:indexes AS i WHERE i.`using` = "gsi"', host=host)
        if not ok:
            raise SystemExit(f"Failed to read system:indexes: {self.errors(body)}")
        states = {}
        for r in rows:
            if r.get("bucket_id"):
                key = (r["bucket_id"], r["scope_id"], r["keyspace_id"], r["name"])
            else:
                key = (r["keyspace_id"], "_default", "_default", r["name"])
            states[key] = r.get("state")
        return states


# ------------------------------------------------------------------ index spec

def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


def validated_keyspaces(spec):
    """Keyspaces the stats checks cover; 'validate: false' ones (load-only buckets) are skipped."""
    return [ks["keyspace"] for ks in spec["keyspaces"] if ks.get("validate", True)]


def spec_indexes(spec):
    """Yields (keyspace, dataset, name, template_name, template, entry) for every index in the spec."""
    for ks in spec["keyspaces"]:
        for entry in ks.get("indexes", []):
            template = spec["templates"][entry["t"]]
            yield ks["keyspace"], ks["dataset"], f"{entry['t']}_{ks['suffix']}", entry["t"], template, entry


def create_statement(spec, keyspace, name, template, entry):
    kind = "VECTOR INDEX" if template.get("kind") == "bhive" else "INDEX"
    statement = f"CREATE {kind} `{name}` ON {keyspace_path(keyspace)}({template['keys']})"
    if template.get("include"):
        statement += f" INCLUDE ({template['include']})"
    with_clause = {"defer_build": True, "num_replica": entry.get("replicas", 0)}
    if entry.get("partitions"):
        statement += " PARTITION BY HASH(META().id)"
        with_clause["num_partition"] = entry["partitions"]
    if template.get("vector"):
        with_clause.update(spec["vector_with"][template["vector"]])
    return f"{statement} WITH {json.dumps(with_clause)}"


def require_indexes(cluster, args):
    """Fail unless every index in --expected_indexes ('bucket.scope.coll=name,...') exists and is online. cbq exits 0 even when a
    CREATE INDEX statement failed, so a test that creates an index with cbq checks it with this. An index that is not online
    yet (pending: "Index creation will be retried in background", or building) is polled for up to --timeout seconds, because
    a CREATE INDEX issued while another build is running on the keyspace is queued by GSI and comes online later."""
    checks = Checks("require_indexes")
    expected = []
    for item in filter(None, (x.strip() for x in (args.expected_indexes or "").split(","))):
        keyspace, name = item.rsplit("=", 1)
        bucket, scope, collection = keyspace.strip().split(".")
        expected.append((bucket, scope, collection, name.strip()))
    if not expected:
        raise SystemExit("--expected_indexes is required, e.g. plasma_holes.scope_0.coll_1=ph_counter")
    deadline, polls = time.time() + args.timeout, 0
    while True:
        states = cluster.index_states()
        waiting = {key: states.get(key) for key in expected if states.get(key) != "online"}
        if not waiting or time.time() > deadline:
            break
        polls += 1
        if polls == 1 or polls % 4 == 0:
            log.info("Waiting for indexes to come online: " +
                     ", ".join(f"{k[3]} on {'.'.join(k[:3])} is {v or 'missing'}" for k, v in waiting.items()))
        time.sleep(15)
    for key, state in waiting.items():
        checks.fail(f"index {key[3]} on {'.'.join(key[:3])} is {state or 'missing'} after {args.timeout}s, expected online")
    checks.report()


def wait_for_docs(cluster, args):
    """Wait until every keyspace in --expected_docs ('bucket.scope.coll=N,...') holds at least N docs and the count
    has stopped changing, so indexes (vector index training in particular) see the fully loaded data. With
    --docs_at_most true it waits until every count is at most N (and stable) instead, for docs that expire or are deleted."""
    checks = Checks("wait_for_docs")
    expected = {}
    for item in filter(None, (x.strip() for x in (args.expected_docs or "").split(","))):
        keyspace, count = item.rsplit("=", 1)
        expected[keyspace.strip()] = int(count)
    if not expected:
        raise SystemExit("--expected_docs is required, e.g. shoes_large._default._default=5000000")

    deadline, previous = time.time() + args.timeout, None
    while True:
        counts = {}
        for keyspace in expected:
            ok, rows, _, _ = cluster.query(f"SELECT RAW COUNT(*) FROM {keyspace_path(keyspace)}", timeout=120,
                                           params={"scan_consistency": "not_bounded"})   # request_plus needs an index on 8.x
            counts[keyspace] = rows[0] if ok and rows else -1
        if args.docs_at_most:
            # waiting for a count to FALL to n or below (TTL expiry, deletes); -1 is an unreadable count
            short = {k: f"{counts[k]}>{n}" for k, n in expected.items() if counts[k] < 0 or counts[k] > n}
        else:
            short = {k: f"{counts[k]}/{n}" for k, n in expected.items() if counts[k] < n}
        if not short and counts == previous:
            log.info("All keyspaces loaded: " + ", ".join(f"{k}={c}" for k, c in sorted(counts.items())))
            break
        if time.time() > deadline:
            checks.fail(f"data load not complete after {args.timeout}s: {short or 'counts still changing'}")
            break
        log.info(f"Waiting for data load: {short or 'counts reached, checking they are stable'}")
        previous = counts
        time.sleep(60)
    checks.report()


def wait_online(cluster, keys, deadline, checks):
    while True:
        states = cluster.index_states()
        pending = [f"{k[-1]}({states.get(k)})" for k in keys if states.get(k) != "online"]
        if not pending:
            return True
        if time.time() > deadline:
            checks.fail(f"{len(pending)} indexes not online before the timeout: {pending[:20]}")
            return False
        log.info(f"Waiting for {len(pending)} indexes to come online: {pending[:10]}")
        time.sleep(30)


def apply_index_spec(cluster, args):
    spec = load_yaml(args.spec)
    checks = Checks("apply_index_spec")
    version = cluster.min_version()
    log.info(f"Cluster versions {cluster.versions()}, lowest {version}")
    existing = cluster.index_states()
    existing_names = {(b, s, c, n) for b, s, c, n in existing}

    # only_if_loaded: a BHIVE index cannot be built without training data, so such a keyspace is left alone while empty
    # (its data is only loaded by runs that use it; after an upgrade from an older source it is still empty)
    only_loaded = {k["keyspace"] for k in spec["keyspaces"] if k.get("only_if_loaded")}
    empty = set()
    for keyspace in sorted(only_loaded):
        # not_bounded: with request_plus a COUNT on a collection without an index fails on 8.x ("No index available"), and an
        # empty collection has no index yet, so the check never saw an empty one (#22: bhive_churn after a 7.6.12 upgrade)
        ok, rows, _, _ = cluster.query(f"SELECT RAW COUNT(1) FROM {keyspace_path(keyspace)}", timeout=600,
                                       params={"scan_consistency": "not_bounded"})
        if ok and rows and rows[0] == 0:
            empty.add(keyspace)
            log.info(f"{keyspace} is empty: its indexes are not created")

    wanted, summary = [], {}
    for keyspace, _, name, tname, template, entry in spec_indexes(spec):
        bucket = keyspace.split(".")[0]
        row = summary.setdefault(bucket, {"eligible": 0, "created": 0, "existing": 0, "skipped": 0})
        if template["min_version"] > version or keyspace in empty:
            row["skipped"] += 1
            continue
        row["eligible"] += 1
        key = tuple(keyspace.split(".")) + (name,)
        wanted.append((keyspace, name, key, entry.get("replicas", 0) + 1))
        if key in existing_names:
            row["existing"] += 1
            continue
        statement = create_statement(spec, keyspace, name, template, entry)
        ok, _, body, _ = cluster.query(statement, timeout=600)
        if ok:
            row["created"] += 1
            log.info(f"Created {statement}")
        elif "already exist" in cluster.errors(body).lower():
            row["existing"] += 1
        else:
            checks.fail(f"{name} on {keyspace}: {cluster.errors(body)}")

    # BUILD deferred indexes in stages: one keyspace per BUILD statement, at most --max_concurrent_builds index
    # instances (replicas included) per stage, and each stage waits until its indexes are online.
    states = cluster.index_states()
    stages, batch, batch_ks, batch_instances = [], [], None, 0
    for keyspace, name, key, instances in wanted:
        if states.get(key) not in ("deferred", "created"):
            continue
        if batch and (keyspace != batch_ks or batch_instances + instances > args.max_concurrent_builds):
            stages.append((batch_ks, batch))
            batch, batch_instances = [], 0
        batch_ks = keyspace
        batch.append((name, key))
        batch_instances += instances
    if batch:
        stages.append((batch_ks, batch))

    deadline = time.time() + args.timeout
    for i, (keyspace, batch) in enumerate(stages, 1):
        names = ", ".join(f"`{n}`" for n, _ in batch)
        log.info(f"Build stage {i}/{len(stages)} on {keyspace}: {names}")
        ok, _, body, _ = cluster.query(f"BUILD INDEX ON {keyspace_path(keyspace)}({names})", timeout=600)
        error = cluster.errors(body)
        if not ok and "retried building in the background" in error:
            # GSI keeps retrying these itself; wait_online below decides whether they made it
            checks.warn(f"BUILD INDEX on {keyspace}: {error}")
        elif not ok and "already" not in error.lower():
            checks.fail(f"BUILD INDEX on {keyspace}: {error}")
            continue
        if not wait_online(cluster, [k for _, k in batch], deadline, checks):
            break
    # Everything the spec wants on this version, including indexes that were already building
    wait_online(cluster, [k for _, _, k, _ in wanted], deadline, checks)

    print_table(["bucket", "eligible", "created now", "already existed", f"skipped (> {version})"],
                [[b, r["eligible"], r["created"], r["existing"], r["skipped"]] for b, r in sorted(summary.items())])
    checks.report()


# ------------------------------------------------------------------ settings, stats, UDFs

def seqscan_disabled(cluster):
    response = cluster.mgmt("GET", "/settings/querySettings")
    response.raise_for_status()
    value = int(response.json().get("queryN1QLFeatCtrl", 0))
    return bool(value & SEQSCAN_BIT), value


def disable_sequential_scans(cluster, args):
    checks = Checks("disable_sequential_scans")
    if cluster.min_version() < 7.6:
        log.info("Sequential scans do not exist before 7.6, nothing to disable")
        return
    disabled, value = seqscan_disabled(cluster)
    if not disabled:
        response = cluster.mgmt("POST", "/settings/querySettings", data={"queryN1QLFeatCtrl": value | SEQSCAN_BIT})
        if response.status_code != 200:
            checks.fail(f"setting queryN1QLFeatCtrl failed: {response.status_code} {response.text}")
        disabled, value = seqscan_disabled(cluster)
    if not disabled:
        checks.fail(f"sequential scan bit not set, queryN1QLFeatCtrl={value}")
    else:
        log.info(f"Sequential scans disabled (queryN1QLFeatCtrl={value})")
    checks.report()


def stats_statements(spec):
    return [f"UPDATE STATISTICS FOR {keyspace_path(ks['keyspace'])}({spec['stats_fields'][ks['dataset']]})"
            for ks in spec["keyspaces"]]


def run_update_statistics(cluster, spec, checks, timeout):
    for statement in stats_statements(spec):
        ok, _, body, elapsed = cluster.query(statement, timeout=timeout)
        if ok:
            log.info(f"{statement} completed in {elapsed:.1f}s")
        else:
            checks.fail(f"{statement} did not complete after {elapsed:.1f}s: {cluster.errors(body)}")


def update_statistics(cluster, args):
    checks = Checks("update_statistics")
    spec = load_yaml(args.spec)
    run_update_statistics(cluster, spec, checks, args.stats_timeout)
    # A successful statement is not enough: the stats must be visible in system:dictionary
    wanted = validated_keyspaces(spec)
    stored = stats_keyspaces(cluster, wanted)
    missing = sorted(set(wanted) - set(stored))
    if missing:
        checks.fail(f"no stored CBO statistics after UPDATE STATISTICS for {missing}")
    else:
        log.info(f"CBO statistics stored for all {len(wanted)} keyspaces: {sorted(set(stored.values()))}")
    checks.report()


CBO_STATS_COLLECTION = "N1QL_SYSTEM_BUCKET.N1QL_SYSTEM_SCOPE.N1QL_CBO_STATS"


def stats_keyspaces(cluster, keyspaces):
    """{keyspace: store} for the given 'bucket.scope.collection' keyspaces that have CBO statistics stored.

    Reads the stats stores, not system:dictionary: system:dictionary only lists what the answering query node has
    cached, so it differs between query nodes and is empty on a freshly added node. Stores:
      - N1QL_SYSTEM_BUCKET.N1QL_SYSTEM_SCOPE.N1QL_CBO_STATS: one document per collection keyed
        'default:<bucket>.<scope>.<collection>' (plus '(histogram)...' / '(index)...' documents), read by key
      - <bucket>._system._query: per-bucket store on versions that keep stats there (also holds 'udf::' docs)"""
    found = {}
    keys = {f"default:{ks}": ks for ks in keyspaces}
    ok, rows, body, _ = cluster.query(f"SELECT RAW META(s).id FROM {keyspace_path(CBO_STATS_COLLECTION)} AS s "
                                      f"USE KEYS $keys", params={"$keys": sorted(keys)})
    if ok:
        for key in rows:
            found[keys[key]] = "N1QL_SYSTEM_BUCKET"
    else:
        log.info(f"{CBO_STATS_COLLECTION} not readable: {cluster.errors(body)}")

    for bucket in sorted({ks.split(".")[0] for ks in keyspaces}):
        ok, rows, body, _ = cluster.query(
            f"SELECT q.`scope`, q.`collection` FROM `{bucket}`.`_system`.`_query` AS q "
            f"WHERE q.docCount IS NOT MISSING AND META(q).id NOT LIKE \"udf::%\"")
        if not ok:
            log.info(f"{bucket}._system._query not readable: {cluster.errors(body)}")
            continue
        for row in rows:
            ks = f"{bucket}.{row.get('scope')}.{row.get('collection')}"
            if ks in keyspaces:
                found.setdefault(ks, "_system._query")
    return found


def create_udfs(cluster, args):
    checks = Checks("create_udfs")
    url = f"{cluster.scheme}://{cluster.host}:{cluster.query_port}/evaluator/v1/libraries/{UDF_JS_LIBRARY}"
    response = requests.post(url, data=UDF_JS_CODE, auth=cluster.auth, timeout=120, verify=False,
                             headers={"Content-Type": "application/json"})
    if response.status_code != 200:
        checks.fail(f"creating JS library {UDF_JS_LIBRARY}: {response.status_code} {response.text}")
    for statement in UDF_STATEMENTS:
        ok, _, body, _ = cluster.query(statement)
        if ok:
            log.info(f"Created {statement}")
        else:
            checks.fail(f"{statement}: {cluster.errors(body)}")
    checks.report()


def udf_names(cluster):
    """The suite's UDFs that exist, or None when system:functions cannot be read (never taken for "no UDFs")."""
    ok, rows, _, _ = cluster.query("SELECT RAW f.identity.name FROM system:functions AS f")
    return sorted(n for n in rows if n in UDF_NAMES) if ok else None


def plan_stability_mode(cluster):
    ok, rows, _, _ = cluster.query("SELECT RAW plan_stability FROM system:settings")
    if ok and rows and isinstance(rows[0], dict):
        return rows[0].get("mode", "off")
    return "off"


def query_metadata_count(cluster):
    """Plan-stability records, or None when they cannot be read (so a failed read is never taken for an empty store).
    not_bounded: with request_plus a COUNT on a collection without an index fails on 8.x."""
    ok, rows, _, _ = cluster.query("SELECT RAW COUNT(*) FROM QUERY_METADATA._system._query",
                                   params={"scan_consistency": "not_bounded"})
    return rows[0] if ok and rows else None


# ------------------------------------------------------------------ baseline

def explain(cluster, statement):
    """(full summary incl. ~subqueries, main-plan summary as system:prepareds exposes it)"""
    ok, rows, body, _ = cluster.query(f"EXPLAIN {statement}")
    if not ok or not rows:
        raise RuntimeError(f"EXPLAIN failed: {cluster.errors(body)}")
    return summarize_plan(rows[0]), summarize_plan(rows[0].get("plan", rows[0]))


def run_timed(cluster, statement, ordered, runs, host=None):
    """One warm-up plus `runs` timed runs: (hash or None if results varied, rows, median_ms)."""
    hashes, timings, count = set(), [], 0
    for attempt in range(runs + 1):
        ok, rows, body, elapsed = cluster.query(statement, host=host)
        if not ok:
            raise RuntimeError(cluster.errors(body))
        hashes.add(result_hash(rows, ordered))
        count = len(rows)
        if attempt:
            timings.append(elapsed * 1000)
    return (hashes.pop() if len(hashes) == 1 else None), count, statistics.median(timings)


def prepare(cluster, name, statement, host=None, delete=True):
    if delete:
        cluster.query("DELETE FROM system:prepareds WHERE name = $n", params={"$n": name})
    ok, _, body, _ = cluster.query(f"PREPARE `{name}` AS {statement}", host=host)
    if not ok:
        raise RuntimeError(f"PREPARE {name}: {cluster.errors(body)}")


def prepared_by_node(cluster, names, query_nodes):
    """{query node: the given prepared statement names cached on it}, or None when system:prepareds is unreadable.
    Rows carry the node that holds them; a node may answer for the whole cluster, so every answer is merged."""
    found = {node: set() for node in query_nodes}
    for node in query_nodes:
        ok, rows, body, _ = cluster.query("SELECT p.name, p.node FROM system:prepareds AS p WHERE p.name IN $names",
                                          host=node, params={"$names": sorted(names)})
        if not ok:
            log.warning(f"system:prepareds not readable on {node}: {cluster.errors(body)}")
            return None
        for row in rows:
            holder = str(row.get("node") or node).rsplit(":", 1)[0].strip("[]")
            if holder in found:
                found[holder].add(row.get("name"))
    return found


PREPARED_FIELDS = ("name", "node", "planPreparedTime", "lastUse", "uses", "indexApiVersion", "featuresControl",
                   "indexScanKeyspaces", "users")


def read_prepareds(cluster, query_nodes, names=None):
    """{(statement name, holder node ip): {PREPARED_FIELDS...}} from system:prepareds, asked on every query node (each
    answers for itself, a node may answer for the whole cluster: the rows are merged by holder). None if unreadable."""
    found = {}
    for node in query_nodes:
        statement = "SELECT " + ", ".join(f"p.{f}" for f in PREPARED_FIELDS) + " FROM system:prepareds AS p"
        params = None
        if names:
            statement += " WHERE p.name IN $names"
            params = {"$names": sorted(names)}
        ok, rows, body, _ = cluster.query(statement, host=node, params=params)
        if not ok:
            log.warning(f"system:prepareds not readable on {node}: {cluster.errors(body)}")
            return None
        for row in rows:
            holder = str(row.get("node") or node).rsplit(":", 1)[0].strip("[]")
            found[(row.get("name"), holder)] = {f: row.get(f) for f in PREPARED_FIELDS}
    return found


def node_overview(cluster):
    """[{node, version, services, uptime_s}] oldest uptime first: a node restarted late (small uptime) primed its prepared
    cache from whoever was up then, so the order explains which statements a node could have copied."""
    pool = cluster.mgmt("GET", "/pools/default").json()
    nodes = [{"node": (n.get("hostname") or "").rsplit(":", 1)[0].strip("[]"), "version": n.get("version"),
              "services": n.get("services"), "uptime_s": int(n.get("uptime") or 0)} for n in pool.get("nodes", [])]
    return sorted(nodes, key=lambda n: -n["uptime_s"])


CR_DEFAULTS = {"queryCompletedThreshold": 1000, "queryCompletedLimit": 4000}


def completed_requests(cluster, args):
    """Record every request of a window in system:completed_requests, then list the vector queries that returned no rows.
    The query service keeps a request only when it ran longer than queryCompletedThreshold (1000 ms), so the empty vector
    results of series 12 (20-56 ms, no error) were never recorded. Modes (--cr_mode):
      start  save the current threshold / limit in --cr_state_file, set the threshold to 0 and the limit to --cr_limit
             (cluster wide, ns_server /settings/querySettings)
      stop   restore the saved values (the defaults 1000 / 4000 if there is no state file)
      report the APPROX_VECTOR_DISTANCE requests recorded since `start`: how many, how many returned no rows without an
             error, and for those the request id, node, time, consistency, phase counts and the plan EXPLAIN gives for the
             same statement. Written in full to --cr_report_file."""
    mode = args.cr_mode
    state = {}
    if os.path.exists(args.cr_state_file):
        try:
            with open(args.cr_state_file) as f:
                state = json.load(f)
        except (OSError, ValueError):
            state = {}
    if mode == "start":
        current = cluster.mgmt("GET", "/settings/querySettings").json()
        previous = {k: current.get(k, CR_DEFAULTS[k]) for k in CR_DEFAULTS}
        if state.get("active") and state.get("previous"):
            previous = state["previous"]            # a second start must not save our own values as the originals
        response = cluster.mgmt("POST", "/settings/querySettings",
                                data={"queryCompletedThreshold": 0, "queryCompletedLimit": args.cr_limit})
        if response.status_code != 200:
            raise SystemExit(f"setting queryCompletedThreshold failed: {response.status_code} {response.text[:200]}")
        _write_json_atomic(args.cr_state_file, {"active": True, "previous": previous, "started_at_ms": int(time.time() * 1000),
                                                "started_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"})
        log.info(f"[completed_requests] recording every request: threshold 0, limit {args.cr_limit} (was {previous})")
    elif mode == "stop":
        previous = state.get("previous") or dict(CR_DEFAULTS)
        response = cluster.mgmt("POST", "/settings/querySettings", data=previous)
        if response.status_code != 200:
            raise SystemExit(f"restoring the completed-requests settings failed: {response.status_code} {response.text[:200]}")
        state["active"] = False
        _write_json_atomic(args.cr_state_file, state)
        log.info(f"[completed_requests] settings restored to {previous}")
    elif mode == "report":
        since_ms = state.get("started_at_ms") or int((time.time() - 1200) * 1000)
        ok, rows, body, _ = cluster.query(
            "SELECT c.requestId, c.node, c.requestTime, c.elapsedTime, c.serviceTime, c.resultCount, c.errorCount, "
            "c.scanConsistency, c.phaseCounts, c.phaseTimes, c.errors, c.statement FROM system:completed_requests c "
            "WHERE c.statement LIKE '%APPROX_VECTOR_DISTANCE%' AND STR_TO_MILLIS(c.requestTime) >= $since "
            "ORDER BY c.requestTime LIMIT 20000", params={"$since": since_ms, "scan_consistency": "not_bounded"})
        if not ok:
            raise SystemExit(f"reading system:completed_requests failed: {cluster.errors(body)}")
        per_keyspace = {}
        for row in rows:
            match = re.search(r"\bfrom\s+([\w.`]+)", row.get("statement", ""), re.I)
            key = (match.group(1).replace("`", "") if match else "?", "empty" if not row.get("resultCount") else "rows")
            per_keyspace[key] = per_keyspace.get(key, 0) + 1
        empty = [r for r in rows if not r.get("resultCount") and not r.get("errorCount")]
        failed = [r for r in rows if r.get("errorCount")]
        log.info(f"[completed_requests] since {state.get('started_at', 'the last 20 minutes')}: {len(rows)} vector requests "
                 f"recorded, {len(empty)} with no rows and no error, {len(failed)} with an error; "
                 f"{', '.join(f'{k[0]} {k[1]}={v}' for k, v in sorted(per_keyspace.items()))}")
        table = []
        for row in empty[:40]:
            try:
                plan = "; ".join(explain(cluster, row["statement"])[0].get("scans", []))
            except Exception as e:
                plan = f"EXPLAIN failed: {str(e)[:60]}"
            row["explain_scans"] = plan
            counts = row.get("phaseCounts") or {}
            table.append([row["requestId"][:8], row.get("node"), row["requestTime"][11:23], row.get("elapsedTime"),
                          row.get("scanConsistency"), json.dumps(counts, sort_keys=True)[:60], plan[:70]])
        if table:
            print_table(["empty request", "node", "at", "elapsed", "consistency", "phaseCounts", "plan now (EXPLAIN)"], table)
        for row in failed[:10]:
            log.info(f"[completed_requests] errored: {row['requestId']} {row['requestTime']} {json.dumps(row.get('errors'))[:200]}")
        _write_json_atomic(args.cr_report_file, {"since": state.get("started_at"), "recorded": len(rows),
                                                 "empty": empty, "failed": failed})
        log.info(f"[completed_requests] full records of {len(empty)} empty and {len(failed)} errored requests in {args.cr_report_file}")
    else:
        raise SystemExit("--cr_mode must be start, stop or report")


def prepareds_state(cluster, args):
    """Which prepared statements each query node holds right now, for troubleshooting a loss after an upgrade: the plan
    time, last use, index API version and features control of every copy, the nodes with version and uptime, written to
    --state_file. With --previous_file (the snapshot taken before the upgrade) it prints what disappeared since, on which
    node, and which fields of the surviving copies changed."""
    taken = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    nodes = node_overview(cluster)
    query_nodes = [n["node"] for n in nodes if "n1ql" in (n["services"] or [])]
    found = read_prepareds(cluster, query_nodes)
    if found is None:
        raise SystemExit("system:prepareds is not readable")
    names = sorted({k[0] for k in found})
    print_table(["node", "version", "services", "uptime s", "prepared statements"],
                [[n["node"], n["version"], ",".join(n["services"] or []), n["uptime_s"],
                  sum(1 for k in found if k[1] == n["node"])] for n in nodes if "n1ql" in (n["services"] or [])])
    log.info(f"[prepareds_state:{args.state_label}] {taken}: {len(names)} distinct statements on {len(query_nodes)} query nodes")
    if args.previous_file and os.path.exists(args.previous_file):
        with open(args.previous_file) as f:
            previous = json.load(f)
        before = {(r["name"], r["node"]): r for r in previous["statements"]}
        before_names = {k[0] for k in before}
        gone = sorted(n for n in before_names if n not in names)
        log.info(f"[prepareds_state:{args.state_label}] compared with {previous.get('label')} ({previous.get('taken_at')}): "
                 f"{len(before_names)} statements then, {len(names)} now, {len(gone)} on no node any more: {gone[:20]}")
        for name in sorted(before_names & set(names)):
            holders = {k[1] for k in found if k[0] == name}
            lacking = [n for n in query_nodes if n not in holders]
            if lacking:
                log.warning(f"[prepareds_state:{args.state_label}] {name} is held by {sorted(holders)} but not by {lacking}")
            for key, now in found.items():
                if key[0] != name:
                    continue
                then = before.get(key)         # the same statement on the same node
                if not then:
                    continue
                for field in ("planPreparedTime", "indexApiVersion", "featuresControl"):
                    if now.get(field) != then.get(field):
                        log.info(f"[prepareds_state:{args.state_label}] {name} on {key[1]}: {field} {then.get(field)} -> "
                                 f"{now.get(field)}")
    elif args.previous_file:
        log.info(f"[prepareds_state:{args.state_label}] {args.previous_file} not found: nothing to compare with")
    if args.state_file:
        _write_json_atomic(args.state_file, {"label": args.state_label, "taken_at": taken, "nodes": nodes,
                                             "statements": [{"name": k[0], "node": k[1], **v} for k, v in sorted(found.items())]})
        log.info(f"[prepareds_state:{args.state_label}] written to {args.state_file}")


def check_prepared_survival(cluster, checks, snapshot, query_nodes, expect):
    """Prepared statements live only in memory: a restarted query node primes its cache from another query node,
    so they survive an upgrade that restarts one query node at a time and are lost when all restart at once.
    expect: true = any loss fails; false = losses warn; auto = fail only when some node kept statements another
    node lost (priming failed), warn when every query node lost them all. Returns False if the survey failed."""
    names = {base["prepared"]["name"] for base in snapshot["queries"].values()}
    cached = prepared_by_node(cluster, names, query_nodes)
    if cached is None:
        checks.warn("prepared: survival not checked (system:prepareds unreadable); EXECUTE decides")
        return False
    missing = {node: sorted(names - have) for node, have in cached.items() if names - have}
    if not missing:
        log.info(f"All {len(names)} prepared statements survived on {len(query_nodes)} query nodes")
        return True
    all_lost = not any(cached.values())
    strict = expect == "true" or (expect == "auto" and not all_lost)
    if all_lost:
        reason = "lost on every query node (all query nodes restarted together)"
    else:
        reason = ("lost while other prepared statements survived (not a restart of every query node: "
                  "cache priming from a peer failed, or eviction)")
    for node, lost in missing.items():
        (checks.fail if strict else checks.warn)(
            f"prepared: {len(lost)}/{len(names)} statements {reason} on {node}: {lost[:10]}")
    report_prepared_loss(cluster, names, query_nodes, missing)
    return True


def report_prepared_loss(cluster, names, query_nodes, missing):
    """What to look at when statements were lost: the nodes with version and uptime (restart order: a node that came up
    late could only copy from nodes that were up), for each lost statement who still holds it with its plan time,
    index API version and features control, and the strings to grep in query.log of the nodes that lost it."""
    try:
        overview = node_overview(cluster)
        print_table(["node", "version", "services", "uptime s (oldest first)"],
                    [[n["node"], n["version"], ",".join(n["services"] or []), n["uptime_s"]] for n in overview])
        found = read_prepareds(cluster, query_nodes, names) or {}
    except Exception as e:      # troubleshooting output must not hide the failure it explains
        log.warning(f"prepared loss report failed: {type(e).__name__}: {e}")
        return
    lost_names = sorted({n for lost in missing.values() for n in lost})
    for name in lost_names:
        holders = {k[1]: v for k, v in found.items() if k[0] == name}
        lost_on = sorted(node for node, lost in missing.items() if name in lost)
        detail = {h: {f: v.get(f) for f in ("planPreparedTime", "lastUse", "uses", "indexApiVersion", "featuresControl")}
                  for h, v in holders.items()}
        log.warning(f"prepared loss: {name} lost on {lost_on}, still held by {sorted(holders) or 'no node'}: {json.dumps(detail)}")
    log.warning("prepared loss: grep the query.log of " + ", ".join(sorted(missing)) + " for these names and for "
                "'prepared', 'prime', 'Prepared'/'plan' errors around the time the node joined; eagle eye's cbcollect "
                "taken after the error has them. Lost: " + ", ".join(lost_names[:20]))


def prepared_plans(cluster, name, query_nodes=None):
    """{holder node ip: plan summary} of a prepared statement on every query node that holds it. Each node is asked (it
    may answer only for itself) and the rows are merged by holder, so a stale copy on one node is not hidden by a fresh
    copy on another."""
    plans = {}
    for node in query_nodes or [None]:
        ok, rows, _, _ = cluster.query("SELECT p.node, META(p).plan AS plan FROM system:prepareds AS p WHERE p.name = $n",
                                       host=node, params={"$n": name})
        for row in rows if ok else []:
            if row.get("plan"):
                holder = str(row.get("node") or node or "?").rsplit(":", 1)[0].strip("[]")
                plans.setdefault(holder, summarize_plan(row["plan"]))
    return plans


def prepared_plan(cluster, name):
    """One copy's plan summary (the baseline, taken right after PREPARE when every copy is the same), or None."""
    plans = prepared_plans(cluster, name)
    return next(iter(plans.values()), None)


def current_plan_changes(main_now, full_now, plan):
    """Differences current optimizer plan -> prepared plan. system:prepareds includes ~subqueries on some versions and
    not on others: compare with whichever matches."""
    return min((diff_plans(now, plan) for now in (main_now, full_now) if now), key=len)


def stalest_plan(main_now, full_now, plans):
    """(holder, plan, changes) of the copy furthest from the current plan: a real change outranks a CBO-only one."""
    judged = [(holder, plan, current_plan_changes(main_now, full_now, plan)) for holder, plan in sorted(plans.items())]
    return max(judged, key=lambda j: (bool(j[2]) and not cbo_only(j[2]), len(j[2])))


def render(statement, samples):
    def substitute(match):
        name, field = match.groups()
        if name not in samples:
            raise KeyError(name)
        value = samples[name] if field is None else samples[name][field]
        return json.dumps(value)
    return PLACEHOLDER_RE.sub(substitute, statement)


def capture_baseline(cluster, args):
    spec, suite = load_yaml(args.spec), load_yaml(args.suite)
    checks = Checks("capture_baseline")
    version = cluster.min_version()

    samples, sample_errors = {}, {}
    for name, statement in suite["samples"].items():
        ok, rows, body, _ = cluster.query(statement, timeout=600)
        if ok and rows and rows[0] is not None:
            samples[name] = rows[0]
        else:
            sample_errors[name] = cluster.errors(body) if not ok else "no rows"

    snapshot = {
        "captured_at": datetime.utcnow().isoformat() + "Z",
        "cluster_versions": cluster.versions(),
        "seqscan_disabled": seqscan_disabled(cluster)[0] if version >= 7.6 else None,
        "plan_stability": plan_stability_mode(cluster),
        "query_metadata_records": 0,
        "udfs": udf_names(cluster),
        "stats_store": stats_keyspaces(cluster, validated_keyspaces(spec)),
        "queries": {},
        "deferred": {},
    }
    if snapshot["udfs"] is None:
        checks.fail("cannot read system:functions: the UDF survival check after the upgrade would have nothing to compare")
        snapshot["udfs"] = []
    if snapshot["plan_stability"] != "off":
        snapshot["query_metadata_records"] = query_metadata_count(cluster)
        if snapshot["query_metadata_records"] is None:
            checks.fail("cannot read QUERY_METADATA._system._query: the plan-stability survival check after the upgrade "
                        "would have nothing to compare")
    snapshot["stats_keyspaces"] = sorted(snapshot["stats_store"])
    missing_stats = sorted(set(validated_keyspaces(spec)) - set(snapshot["stats_keyspaces"]))
    if missing_stats:
        checks.fail(f"no CBO statistics for {missing_stats}: the stats-migration checks after the upgrade "
                    f"would have nothing to compare (run update_statistics first)")

    table = []
    for q in suite["queries"]:
        name = q["name"]
        try:
            statement = render(q["statement"], samples)
        except KeyError as e:
            checks.fail(f"{name}: sample {e.args[0]} unavailable ({sample_errors.get(e.args[0])})")
            continue
        if q.get("min_version", 0) > version:
            snapshot["deferred"][name] = {"statement": statement, "min_version": q["min_version"]}
            table.append([name, "deferred", "", "", f"needs {q['min_version']}"])
            continue
        try:
            plan, main_plan = explain(cluster, statement)
            digest, rows, median_ms = run_timed(cluster, statement, q.get("ordered", False), args.runs)
            if q.get("hash") and digest is None:
                # hash: true marks a deterministic query on static data: results that change between identical runs
                # would leave the query uncompared for the whole upgrade, so the baseline is not usable
                checks.fail(f"{name}: results differ between identical runs (hash: true expects identical results)")
            pname = f"upq_{name}"
            prepare(cluster, pname, statement)
            ok, prows, body, _ = cluster.query(f"EXECUTE `{pname}`")
            if not ok:
                raise RuntimeError(f"EXECUTE {pname}: {cluster.errors(body)}")
            if q.get("hash") and digest and result_hash(prows, q.get("ordered", False)) != digest:
                checks.fail(f"{name}: prepared result differs from ad-hoc result")
        except RuntimeError as e:
            checks.fail(f"{name}: {e}")
            continue
        snapshot["queries"][name] = {
            "statement": statement, "ordered": q.get("ordered", False),
            "hash": digest if q.get("hash") else None, "rows": rows, "median_ms": round(median_ms, 2),
            "plan": plan, "main_plan": main_plan,
            "prepared": {"name": pname, "plan": prepared_plan(cluster, pname)},
        }
        table.append([name, rows, round(median_ms, 1), "; ".join(plan["scans"]), " ".join(plan["joins"])])

    with open(args.snapshot_file, "w") as f:
        json.dump(snapshot, f, indent=2, sort_keys=True)
    print_table(["query", "rows", "median ms", "scans", "joins"], table)
    log.info(f"Baseline: {len(snapshot['queries'])} queries captured, {len(snapshot['deferred'])} deferred, "
             f"versions {snapshot['cluster_versions']}, plan stability {snapshot['plan_stability']}, "
             f"UDFs {snapshot['udfs']}, written to {args.snapshot_file}")
    checks.report()


def load_snapshot(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"{path} not found: run capture_baseline before the upgrade on the same sequoia client "
                         f"with volumes /data:/data")


def probe_statement(spec, ks):
    """A query on the keyspace the optimizer has to cost from its statistics: a filter on the leading field of one
    of its scalar indexes, where that field has distribution stats (stats_fields). None if no index qualifies."""
    stats_fields = {f.strip() for f in spec["stats_fields"][ks["dataset"]].split(",")}
    for entry in ks.get("indexes", []):
        template = spec["templates"][entry["t"]]
        if template.get("vector"):
            continue
        match = re.match(r"`?(\w+)`?\s*(,|$|INCLUDE MISSING)", template["keys"])
        if match and match.group(1) in stats_fields:
            return (f"SELECT RAW COUNT(1) FROM {keyspace_path(ks['keyspace'])} AS d "
                    f"WHERE d.`{match.group(1)}` IS NOT NULL")
    return None


def validate_statistics(cluster, args):
    spec, snapshot = load_yaml(args.spec), load_snapshot(args.snapshot_file)
    checks = Checks("validate_statistics")
    # A stuck stats migration (CBSE-23292) blocks queries outright, so probe every keyspace first, on every query
    # node (each keeps its own stats cache), with a filter the optimizer has to cost from the keyspace's statistics
    query_nodes = cluster.query_nodes()
    for ks in spec["keyspaces"]:
        if ks.get("validate") is False:
            continue
        statement = probe_statement(spec, ks)
        if statement is None:
            checks.fail(f"probe on {ks['keyspace']}: no scalar index on a stats field to build the probe from")
            continue
        for node in query_nodes:
            ok, rows, body, elapsed = cluster.query(f"EXPLAIN {statement}", host=node, timeout=120)
            if not ok:
                checks.fail(f"probe on {ks['keyspace']} via {node}: EXPLAIN failed after {elapsed:.1f}s: "
                            f"{cluster.errors(body)}")
                continue
            costed = summarize_plan(rows[0])["cbo"] if rows else False
            ok, rows, body, elapsed = cluster.query(statement, host=node, timeout=120)
            if not ok:
                checks.fail(f"probe on {ks['keyspace']} via {node} failed after {elapsed:.1f}s: {cluster.errors(body)}")
            elif not costed:
                checks.warn(f"probe on {ks['keyspace']} via {node}: plan not costed by CBO (statistics not used)")
            else:
                log.info(f"probe on {ks['keyspace']} via {node}: {rows[0] if rows else 0} docs in {elapsed:.1f}s, "
                         f"CBO-costed")
    stored = stats_keyspaces(cluster, snapshot["stats_keyspaces"])
    lost = sorted(set(snapshot["stats_keyspaces"]) - set(stored))
    if lost:
        checks.fail(f"CBO statistics lost across the upgrade for {lost}")
    else:
        before = snapshot.get("stats_store", {})
        moved = sorted({f"{before.get(k)} -> {v}" for k, v in stored.items() if before.get(k) and before[k] != v})
        log.info(f"CBO statistics present for all {len(snapshot['stats_keyspaces'])} keyspaces captured pre-upgrade"
                 + (f", migrated {moved}" if moved else f", store unchanged {sorted(set(stored.values()))}"))
    run_update_statistics(cluster, spec, checks, args.stats_timeout)
    checks.report()


def validate_baseline(cluster, args):
    snapshot = load_snapshot(args.snapshot_file)
    checks = Checks("validate_baseline")
    versions = cluster.versions()
    version = cluster.min_version()
    log.info(f"Baseline from {snapshot['captured_at']} on {snapshot['cluster_versions']}, cluster now {versions}")
    if versions == snapshot["cluster_versions"]:
        checks.warn(f"cluster version unchanged ({versions}); was the upgrade done?")

    # Settings and objects that must survive the upgrade
    if snapshot.get("seqscan_disabled") and not seqscan_disabled(cluster)[0]:
        checks.fail("sequential scans were disabled before the upgrade and are enabled now")
    udfs_now = udf_names(cluster)
    if udfs_now is None:
        checks.fail("cannot read system:functions after the upgrade: UDF survival not checked")
        udfs_now = snapshot.get("udfs", [])
    missing_udfs = sorted(set(snapshot.get("udfs", [])) - set(udfs_now))
    if missing_udfs:
        checks.fail(f"UDFs missing after the upgrade: {missing_udfs}")
    stability = plan_stability_mode(cluster)
    if snapshot.get("plan_stability", "off") != "off":
        if stability != snapshot["plan_stability"]:
            checks.fail(f"plan stability mode {snapshot['plan_stability']} -> {stability}")
        if snapshot.get("query_metadata_records"):
            records = query_metadata_count(cluster)
            if records is None:
                checks.fail("cannot read QUERY_METADATA._system._query after the upgrade")
            elif not records:
                checks.fail("QUERY_METADATA._system._query had plan-stability records and is empty now")

    global EQUIVALENT_INDEXES
    EQUIVALENT_INDEXES = equivalence_map(load_yaml(args.spec))
    query_nodes = cluster.query_nodes()
    # Survival is judged before anything below re-prepares (a PREPARE is distributed to the other query nodes)
    surveyed = check_prepared_survival(cluster, checks, snapshot, query_nodes, args.expect_prepared_survive)
    table = []
    for name, base in snapshot["queries"].items():
        row = [name, "same", "same", "", "ok"]
        try:
            full_now, main_now = explain(cluster, base["statement"])
            changes = diff_plans(base["plan"], full_now)
            if cbo_only(changes):
                row[1] = "CBO"
                checks.warn(f"plan: {name}: {'; '.join(changes)}")
            elif changes and source_without_cbo(snapshot):
                # CBO is off by default before 7.6 and on after, so a different join order is expected (MB-63204);
                # results and latency are still checked below
                row[1] = "CHANGED-CBO"
                checks.warn(f"plan: {name}: {'; '.join(changes)} [source version had no default CBO]")
            elif only_equivalent_index_swaps(base["plan"], full_now):
                row[1] = "EQUIV-INDEX"
                checks.warn(f"plan: {name}: {'; '.join(changes)} [equivalent indexes: index_spec.yml equivalent_indexes]")
            elif changes:
                row[1] = "CHANGED"
                (checks.fail if args.fail_on_plan_change else checks.warn)(f"plan: {name}: {'; '.join(changes)}")
        except RuntimeError as e:
            full_now = main_now = None
            row[1] = "ERROR"
            checks.fail(f"plan: {name}: {e}")

        medians = []
        for node in query_nodes:
            try:
                digest, rows, median_ms = run_timed(cluster, base["statement"], base["ordered"], args.runs, host=node)
                medians.append(median_ms)
                if base["hash"] and digest != base["hash"]:
                    row[2] = "DIFF"
                    checks.fail(f"result: {name} on {node}: {rows} rows (baseline {base['rows']}), different hash")
            except RuntimeError as e:
                row[2] = "ERROR"
                checks.fail(f"result: {name} on {node}: {e}")
        if medians:
            post_ms = max(medians)
            row[3] = f"{base['median_ms']} -> {post_ms:.1f}"
            if post_ms > max(base["median_ms"] * args.latency_ceiling, base["median_ms"] + 50):
                row[3] += " SLOW"
                checks.warn(f"latency: {name} {base['median_ms']}ms -> {post_ms:.1f}ms (> {args.latency_ceiling}x)")

        row[4] = validate_prepared(cluster, checks, name, base, full_now, main_now, query_nodes, snapshot, surveyed)
        table.append(row)
    print_table(["query", "plan", "result", "latency ms (pre -> post)", "prepared"], table)

    # Queries the initial version could not run need indexes apply_index_spec only creates after this check;
    # run_suite executes them once the final version supports them and suite_report fails on their errors
    runnable = sorted(n for n, d in snapshot.get("deferred", {}).items() if d["min_version"] <= version)
    if runnable:
        log.info(f"new-feature queries {runnable} are validated by run_suite after apply_index_spec")
    checks.report()


def validate_prepared(cluster, checks, name, base, full_now, main_now, query_nodes, snapshot, surveyed):
    pname = base["prepared"]["name"]
    status = "ok"
    for node in query_nodes:
        ok, rows, body, _ = cluster.query(f"EXECUTE `{pname}`", host=node)
        if not ok and 4040 in cluster.error_codes(body):
            message = f"prepared: {pname} missing on {node} after the upgrade, re-preparing"
            if surveyed:
                log.info(message)  # check_prepared_survival already reported (and judged) the losses it found
            else:
                checks.warn(message)
            status = "re-prepared"
            try:
                # Prepare on the node that lost it: distribution from another node is asynchronous, and the
                # DELETE in a plain prepare() would also drop the copies on the nodes already checked
                prepare(cluster, pname, base["statement"], host=node, delete=False)
            except RuntimeError as e:
                checks.fail(f"prepared: {e}")
                return "ERROR"
            ok, rows, body, _ = cluster.query(f"EXECUTE `{pname}`", host=node)
        if not ok:
            checks.fail(f"prepared: EXECUTE {pname} on {node}: {cluster.errors(body)}")
            return "ERROR"
        if base["hash"] and result_hash(rows, base["ordered"]) != base["hash"]:
            checks.fail(f"prepared: EXECUTE {pname} on {node} returned different results than the baseline")
            status = "DIFF"

    plans = prepared_plans(cluster, pname, query_nodes)
    if not plans:
        checks.warn(f"prepared: {pname} plan not readable from system:prepareds")
        return status
    if snapshot.get("plan_stability", "off") != "off":
        # Plan stability must keep the pre-upgrade prepared plan, on every query node
        pinned = base["prepared"].get("plan")
        for holder, plan in sorted(plans.items()):
            if pinned and diff_plans(pinned, plan):
                checks.fail(f"prepared: {pname} plan on {holder} changed despite plan stability: "
                            f"{'; '.join(diff_plans(pinned, plan))}")
                status = "CHANGED"
    elif main_now:
        # Without plan stability the prepared statement must not keep serving a stale plan (CBSE-21288) on any node:
        # judge the copy furthest from the current plan
        holder, plan_now, changes = stalest_plan(main_now, full_now, plans)
        message = (f"prepared: {pname} on {holder} serves a plan different from the current optimizer plan "
                   f"(current -> prepared): {'; '.join(changes)}")
        if cbo_only(changes):
            checks.warn(message)
            status = "STALE-CBO"
        elif changes and source_without_cbo(snapshot):
            # Default behaviour, not a bug (MB-63204): a prepared plan is only re-prepared automatically when
            # n1ql-feat-ctrl bit 23 (opt-in, off in production) is set, and CBO is off by default before 7.6, so
            # a join order chosen by 7.2 stays until the statement is re-prepared.
            checks.warn(f"{message} [source version had no default CBO: expected, re-prepare is checked next]")
            status = reprepare_stale(cluster, checks, pname, base, main_now, full_now)
        elif changes and any(only_equivalent_index_swaps(now, plan_now) for now in (main_now, full_now) if now):
            checks.warn(f"{message} [equivalent indexes: index_spec.yml equivalent_indexes]")
            status = "STALE-EQUIV"
        elif changes:
            checks.fail(message)
            status = "STALE"
    return status


def source_without_cbo(snapshot):
    """CBO is on by default from 7.6; a plan from an older source differs after the upgrade by design."""
    versions = [version_float(v) for v in snapshot.get("cluster_versions", [])]
    return bool(versions) and min(versions) < 7.6


def reprepare_stale(cluster, checks, pname, base, main_now, full_now):
    """The documented way to refresh a stale prepared plan (MB-63204, 8.0+): UNSET planPreparedTime makes the
    statement re-prepare on its next execution. It must then return the baseline results and serve the current plan."""
    if cluster.min_version() < 8.0:
        return "STALE-DEFAULT"
    ok, _, body, _ = cluster.query("UPDATE system:prepareds UNSET planPreparedTime WHERE name = $n",
                                   params={"$n": pname})
    if not ok:
        checks.fail(f"prepared: {pname} UNSET planPreparedTime failed: {cluster.errors(body)}")
        return "STALE"
    query_nodes = cluster.query_nodes()
    for node in query_nodes:
        ok, rows, body, _ = cluster.query(f"EXECUTE `{pname}`", host=node)
        if not ok:
            checks.fail(f"prepared: EXECUTE {pname} on {node} after UNSET planPreparedTime: {cluster.errors(body)}")
            return "ERROR"
        if base["hash"] and result_hash(rows, base["ordered"]) != base["hash"]:
            checks.fail(f"prepared: {pname} on {node} returned different results after the re-prepare")
            return "DIFF"
    plans = prepared_plans(cluster, pname, query_nodes)
    if not plans:
        checks.warn(f"prepared: {pname} plan not readable after the re-prepare")
        return "STALE-DEFAULT"
    holder, _, changes = stalest_plan(main_now, full_now, plans)
    if changes and not cbo_only(changes):
        checks.fail(f"prepared: {pname} on {holder} still serves a stale plan after UNSET planPreparedTime "
                    f"(current -> prepared): {'; '.join(changes)}")
        return "STALE"
    log.info(f"prepared: {pname} re-prepared with UNSET planPreparedTime and now serves the current plan")
    return "RE-PREPARED"


# ------------------------------------------------------------------ continuous suite run (post-upgrade)

def suite_run_file(args):
    return args.snapshot_file.replace(".json", "_suite_run.json")


def _note(bucket, name, message, keep=20):
    entry = bucket.setdefault(name, {"count": 0, "samples": [], "times": []})
    entry["count"] += 1
    if len(entry["samples"]) < keep:
        entry["samples"].append(message[:300])
        entry.setdefault("times", []).append(datetime.utcnow().isoformat(timespec="seconds"))     # UTC, one per sample


def _write_json_atomic(path, data):
    # write-then-rename so a container removed mid-write never leaves a truncated file behind
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def run_suite(cluster, args):
    """Loop the captured statements (plus deferred ones the cluster now supports) on all query nodes until
    --duration expires. Static-bucket results must keep matching the baseline hash, including while indexes move
    during rebalances and while nodes are swapped during an online upgrade. Survives the node it talks to leaving
    the cluster. Progress is written after every pass so suite_report works even if the container is removed."""
    snapshot = load_snapshot(args.snapshot_file)
    version = cluster.min_version()
    queries = [(name, q["statement"], q["ordered"], q["hash"]) for name, q in snapshot["queries"].items()]
    queries += [(name, d["statement"], False, None) for name, d in snapshot.get("deferred", {}).items()
                if d["min_version"] <= version]
    result = {"passes": 0, "executions": 0, "errors": {}, "mismatches": {}, "started": datetime.utcnow().isoformat()}
    # Replace any earlier run's file now (/data persists across runs and phases), so suite_report sees "no pass
    # completed" rather than judging an older run if this one never finishes a pass
    _write_json_atomic(suite_run_file(args), result)
    known_nodes = cluster.query_nodes()
    deadline = time.time() + args.duration
    while time.time() < deadline:
        # the REST host may have been swapped out of the cluster: fall back to any query node seen before
        nodes = None
        for host in [cluster.host] + [n for n in known_nodes if n != cluster.host]:
            try:
                cluster.host = host
                nodes = cluster.query_nodes()
                break
            except Exception:
                continue
        if not nodes:
            _note(result["errors"], "_cluster", "no query node reachable")
            time.sleep(30)
            continue
        known_nodes = sorted(set(known_nodes) | set(nodes))
        for node in nodes:
            for name, statement, ordered, digest in queries:
                ok, rows, body, _ = cluster.query(statement, host=node)
                result["executions"] += 1
                if not ok:
                    _note(result["errors"], name, f"{node}: {cluster.errors(body)}")
                elif digest and result_hash(rows, ordered) != digest:
                    _note(result["mismatches"], name, f"{node}: {len(rows)} rows")
        result["passes"] += 1
        result["updated"] = datetime.utcnow().isoformat()
        _write_json_atomic(suite_run_file(args), result)
        log.info(f"pass {result['passes']}: {result['executions']} executions, "
                 f"{sum(e['count'] for e in result['errors'].values())} errors, "
                 f"{sum(e['count'] for e in result['mismatches'].values())} result mismatches")


def suite_report(cluster, args):
    checks = Checks("suite_report")
    try:
        with open(suite_run_file(args)) as f:
            result = json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"{suite_run_file(args)} not found: run_suite did not complete a pass")
    log.info(f"run_suite: {result['passes']} passes, {result['executions']} executions")
    for name, entry in result["mismatches"].items():
        checks.fail(f"{name}: results differed from the baseline {entry['count']} time(s): {entry['samples'][:5]}")
    for name, entry in result["errors"].items():
        (checks.fail if args.fail_on_query_error else checks.warn)(
            f"{name}: {entry['count']} error(s): {entry['samples'][:3]}")
    label_errors_by_rebalance(result)
    if not result["passes"]:
        checks.fail("run_suite did not complete a single pass")
    checks.report()


def label_errors_by_rebalance(result, margin=60):
    """Logs every recorded query error with its time (UTC) and whether it fell inside a rebalance window (+- margin
    seconds) written by rebalance_in / rebalance_out, so a transient error during a topology change can be told from one
    in a quiet cluster. Only logging: whether such errors fail the run stays with --fail_on_query_error."""
    windows = []
    if os.path.exists(REBALANCE_WINDOWS_FILE):
        try:
            with open(REBALANCE_WINDOWS_FILE) as f:
                windows = json.load(f)
        except (OSError, ValueError):
            pass
    def parse(text):
        return datetime.fromisoformat(text)
    rows, inside, outside = [], 0, 0
    for name, entry in sorted(result["errors"].items()):
        for message, when in zip(entry["samples"], entry.get("times", [])):
            moment = parse(when)
            hit = next((w for w in windows if (parse(w["start"]) - timedelta(seconds=margin)) <= moment
                        <= (parse(w["end"]) + timedelta(seconds=margin))), None)
            inside, outside = inside + bool(hit), outside + (not hit)
            rows.append([name, when, f"rebalance {hit['start'][11:]}..{hit['end'][11:]} ejecting {hit['ejected'] or '-'}"
                         if hit else "no rebalance running", message[:110]])
    if rows:
        print_table(["query", "at (UTC)", "rebalance at that time", "error"], rows)
        log.info(f"{inside} of {inside + outside} recorded query errors fell inside a rebalance window "
                 f"({len(windows)} windows recorded, margin {margin}s)")
    elif result["errors"]:
        log.info("query errors recorded without times (run by an older image): nothing to compare with the rebalance windows")


# ------------------------------------------------------------------ index DDL while the cluster is mixed-version

DDL_KEYSPACE = "ddl_scratch._default._default"
DDL_IDLE_POLL = 10  # seconds between version checks while the cluster is not mixed-version
# (shape, index keys, partition clause, WITH options, field the check query filters on)
DDL_SHAPES = [
    ("scalar", "(`city`)", "", {"num_replica": 0}, "city"),
    ("partitioned", "(`country`, `city`)", " PARTITION BY HASH(META().id)", {"num_replica": 0, "num_partition": 4}, "country"),
    ("replica", "(`price`, `city`)", "", {"num_replica": 1}, "price"),
]


def ddl_run_file(args):
    return args.ddl_file


def ddl_round(cluster, n, host, timeout):
    """One create / build / query / drop of a throwaway index. Returns (index name, error or None). The index is
    dropped even when a later step failed, so a failed round does not leave it behind."""
    shape, keys, partition, with_options, field = DDL_SHAPES[n % len(DDL_SHAPES)]
    name = f"ddl_{n}_{shape}"
    path = keyspace_path(DDL_KEYSPACE)
    key = tuple(DDL_KEYSPACE.split(".")[:1]) + ("_default", "_default", name)
    error = None
    ok, _, body, _ = cluster.query(f"CREATE INDEX `{name}` ON {path}{keys}{partition} "
                                   f"WITH {json.dumps(dict(with_options, defer_build=True))}", host=host)
    if not ok:
        return name, f"create {shape}: {cluster.errors(body)}"
    ok, _, body, _ = cluster.query(f"BUILD INDEX ON {path}(`{name}`)", host=host)
    if not ok:
        error = f"build {shape}: {cluster.errors(body)}"
    else:
        deadline = time.time() + timeout
        while True:
            try:
                state = cluster.index_states(host).get(key)
            except SystemExit as e:
                state, error = None, f"state {shape}: {e}"
                break
            if state == "online":
                break
            if time.time() > deadline:
                error = f"{shape} index not online after {timeout}s (state {state})"
                break
            time.sleep(5)
        if not error:
            ok, rows, body, _ = cluster.query(f"SELECT RAW COUNT(1) FROM {path} USE INDEX (`{name}`) "
                                              f"WHERE `{field}` IS NOT NULL", host=host)
            if not ok:
                error = f"query {shape}: {cluster.errors(body)}"
    ok, _, body, _ = cluster.query(f"DROP INDEX `{name}` ON {path}", host=host)
    if not ok and not error:
        error = f"drop {shape}: {cluster.errors(body)}"
    return name, error


def run_ddl(cluster, args):
    """Offline upgrade only: DDL is not allowed during a rebalance, and an offline (in place) upgrade has none.
    Loops create / build / query / drop of a throwaway index on a scratch bucket, but only while the cluster is
    mixed-version (some nodes upgraded, some not), until --duration expires. Progress is written after every round
    so ddl_report works even if the container is removed."""
    result = {"rounds": 0, "completed": 0, "errors": {}, "in_flight": None, "started": datetime.utcnow().isoformat()}
    known_nodes = [cluster.host]
    deadline = time.time() + args.duration
    _write_json_atomic(ddl_run_file(args), result)  # so ddl_report can tell "no round ran" from "never started"
    while time.time() < deadline:
        mixed = None
        for host in [cluster.host] + [n for n in known_nodes if n != cluster.host]:
            try:
                cluster.host = host
                nodes = cluster.nodes()
                known_nodes = sorted(set(known_nodes) | {n["hostname"].rsplit(":", 1)[0].strip("[]") for n in nodes})
                mixed = len({n.get("version", "") for n in nodes}) > 1
                break
            except Exception:
                continue
        if not mixed:
            time.sleep(DDL_IDLE_POLL)
            continue
        n = result["rounds"]
        result["rounds"] += 1
        result["in_flight"] = f"ddl_{n}_{DDL_SHAPES[n % len(DDL_SHAPES)][0]}"
        _write_json_atomic(ddl_run_file(args), result)
        name, error = ddl_round(cluster, n, cluster.host, args.timeout)
        result["in_flight"] = None
        if error:
            _note(result["errors"], name, error)
        else:
            result["completed"] += 1
        result["updated"] = datetime.utcnow().isoformat()
        _write_json_atomic(ddl_run_file(args), result)
        log.info(f"round {result['rounds']}: {result['completed']} completed, "
                 f"{sum(e['count'] for e in result['errors'].values())} errors")
        time.sleep(args.ddl_pause)


def ddl_report(cluster, args):
    checks = Checks("ddl_report")
    try:
        with open(ddl_run_file(args)) as f:
            result = json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"{ddl_run_file(args)} not found: run_ddl did not start")
    log.info(f"run_ddl: {result['rounds']} rounds during the mixed-version window, {result['completed']} completed")
    # An offline upgrade restarts every node in place, so a DDL round in the mixed-version window can lose its KV /
    # indexer / query connection: those errors are expected and only warn. An index that never came online is not.
    for name, entry in result["errors"].items():
        stuck = any("not online after" in s for s in entry["samples"])
        (checks.fail if stuck else checks.warn)(f"{name}: {entry['count']} error(s): {entry['samples'][:3]}")
    if not result["rounds"]:
        checks.warn("no DDL round ran while the cluster was mixed-version (was the window too short, "
                    "or was run_ddl removed before the upgrade started?)")
    # The container is removed without warning: a round may have been interrupted. Drop whatever is left.
    left = sorted(k[-1] for k in cluster.index_states() if k[0] == DDL_KEYSPACE.split(".")[0] and k[-1].startswith("ddl_"))
    for name in left:
        if name == result.get("in_flight"):
            checks.warn(f"{name}: round interrupted when run_ddl was stopped, dropped")
        elif name in result["errors"]:
            checks.warn(f"{name}: left behind after a failed round (see its error above), dropped")
        else:
            checks.fail(f"{name}: left behind by run_ddl, dropped")
        ok, _, body, _ = cluster.query(f"DROP INDEX `{name}` ON {keyspace_path(DDL_KEYSPACE)}")
        if not ok:
            checks.fail(f"{name}: could not be dropped: {cluster.errors(body)}")
    checks.report()


# ------------------------------------------------------------------ plasma holes and BHIVE churn: the checks
# CBSE-23065, MB-65842, MB-68945. The workload (magmaloader loads and deletes, churn_keyspaces, light writes), the reading of the storage stats
# (report_storage_stats) and the wait for the indexers to drain (wait_until_mutations_processed) are indexmanager actions;
# what is here judges the JSON files report_storage_stats wrote ({captured_at, prefix, instances, timeline}), because the
# before / after comparison is specific to an upgrade.

PLASMA_BUCKET = "plasma_holes"
PLASMA_SCOPE = "scope_0"   # coll_0 scatter, coll_1 range, coll_2 keymove, coll_3 expiry (see the pre-upgrade test)
BHIVE_BUCKET = "bhive_churn"
# real BigANN vectors (magmaloader --sift_path) in scope scope_0; query_manager only picks scope_* / coll_* collections
BHIVE_COLLECTIONS = {"coll_0": "scatter", "coll_1": "range"}


def load_stats(path):
    """A report_storage_stats file: instances = the last read, timeline = every read ({at, instances})."""
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"{path} not found: run indexmanager report_storage_stats with --storage_stats_file {path} "
                         f"(volumes /data:/data)")


def plasma_totals(instances):
    """Sums over instances that report num_pages (BHIVE / vector stores do not). density = live items per page."""
    totals = {"instances": 0, "pages": 0, "items": 0, "records": 0, "empty_pages": 0, "hf_empty": 0, "hf_holes": 0,
              "merged_empty": 0, "purges": 0, "hole_stats": False}
    for stats in instances.values():
        if not stats.get("num_pages"):
            continue
        totals["instances"] += 1
        totals["pages"] += stats["num_pages"]
        totals["items"] += stats.get("items_count") or 0
        totals["records"] += stats.get("total_records") or 0
        if stats.get("num_empty_pages") is not None:
            totals["hole_stats"] = True
        totals["empty_pages"] += stats.get("num_empty_pages") or 0
        totals["hf_empty"] += stats.get("hf_num_empty") or 0
        totals["hf_holes"] += stats.get("hf_num_holes") or 0
        totals["merged_empty"] += stats.get("merges_emptypages") or 0
        totals["purges"] += stats.get("purges") or 0
    totals["density"] = round(totals["items"] / totals["pages"], 1) if totals["pages"] else None
    return totals


def plasma_by_collection(instances):
    groups = {}
    for key, stats in instances.items():
        index = key.split("|")[1]                       # bucket:scope:collection:index
        parts = index.split(":")
        groups.setdefault(parts[2] if len(parts) >= 4 else "_default", {})[key] = stats
    return {name: plasma_totals(group) for name, group in sorted(groups.items())}


def print_plasma(title, by_collection):
    rows = [[name, t["instances"], t["pages"], t["items"], t["density"], t["empty_pages"], t["hf_empty"], t["hf_holes"],
             t["merged_empty"], t["purges"]] for name, t in by_collection.items()]
    print_table([title, "instances", "pages", "items", "items/page", "empty pages", "hf empty", "hf holes", "merged empty",
                 "purges"], rows)


def plasma_grand_total(by_collection):
    keys = ("instances", "pages", "items", "records", "empty_pages", "hf_empty", "hf_holes", "merged_empty", "purges")
    total = {k: sum(t[k] for t in by_collection.values()) for k in keys}
    total["hole_stats"] = any(t["hole_stats"] for t in by_collection.values())
    total["density"] = round(total["items"] / total["pages"], 1) if total["pages"] else None
    return total


def capture_plasma_state(cluster, args):
    """Before the upgrade, once the holes exist (indexmanager report_storage_stats --wait_empty_pages wrote --stats_file):
    check the holes are there and keep the page counts and hole stats for validate_plasma."""
    checks = Checks("capture_plasma_state")
    instances = load_stats(args.stats_file)["instances"]
    if not instances:
        raise SystemExit(f"no {PLASMA_BUCKET} index instances in {args.stats_file}")
    by_collection = plasma_by_collection(instances)
    print_plasma("pre-upgrade", by_collection)
    for name, totals in by_collection.items():
        if totals["density"] is not None and totals["density"] > args.plasma_bloat_density:
            checks.warn(f"{name}: {totals['density']} live items per page before the upgrade: the holes were not "
                        f"created (expected below {args.plasma_bloat_density})")
    snapshot = {"captured_at": datetime.utcnow().isoformat() + "Z", "cluster_versions": cluster.versions(),
                "instances": instances, "collections": by_collection}
    _write_json_atomic(args.plasma_file, snapshot)
    log.info(f"Captured {len(instances)} {PLASMA_BUCKET} index instances to {args.plasma_file}")
    checks.report()


def plasma_scans(cluster, args):
    """A full scan of every plasma_holes index: readers hint the purger and hole cleaner (MB-65842). The indexes come from
    indexmanager create_n_indexes_on_buckets, so their names are random: they are read from system:indexes. An index is
    scanned on its first key when that is a plain field (array and expression keys are skipped)."""
    checks = Checks("plasma_scans")
    ok, rows, body, _ = cluster.query("SELECT name, scope_id, keyspace_id, index_key FROM system:indexes "
                                      f'WHERE bucket_id = "{PLASMA_BUCKET}" AND `using` = "gsi" AND state = "online"')
    if not ok:
        checks.fail(f"could not list the {PLASMA_BUCKET} indexes: {cluster.errors(body)}")
        checks.report()
        return
    scanned = 0
    for row in rows:
        keys = row.get("index_key") or []
        match = re.match(r"^`(\w+)`(?: INCLUDE MISSING)?(?: ASC| DESC)?$", keys[0]) if keys else None
        if not match:
            continue
        path = keyspace_path(f"{PLASMA_BUCKET}.{row['scope_id']}.{row['keyspace_id']}")
        ok, _, body, _ = cluster.query(f"SELECT RAW COUNT(1) FROM {path} USE INDEX (`{row['name']}`) "
                                       f"WHERE `{match.group(1)}` IS NOT NULL", timeout=1800)
        scanned += 1
        if not ok:
            checks.fail(f"{row['keyspace_id']}: scan on {row['name']}: {cluster.errors(body)}")
    log.info(f"Scanned {scanned} of {len(rows)} {PLASMA_BUCKET} indexes")
    if not scanned:
        checks.warn(f"no {PLASMA_BUCKET} index with a plain first key was found: nothing was scanned")
    checks.report()


def validate_plasma(cluster, args):
    """After the upgrade, against the capture_plasma_state snapshot, from the files indexmanager report_storage_stats wrote:
    --stats_after (right after the upgrade), --stats_timeline (comma separated files of reads over time: no scans, then after
    full scans, then the final watch) and --stats_final (the last read of a watch that starts after the light writes and the
    drain wait). The drain wait is wait_until_mutations_processed: writers not throttled (the Citi symptom) fails that container.
    1. nothing was lost: every collection still has its index instances and the same live item count
    2. the timeline is printed: pages, density, empty pages, purges
    3. empty pages that stay are a warning (--plasma_fail_on_empty true makes them a failure). They are judged at the end of
       the final watch, because the purger and the hole cleaner work when there are writes (series 12, #25: no purger run in
       the 40 idle minutes), and the message says whether the empty pages fell during that watch."""
    checks = Checks("validate_plasma")
    if not os.path.exists(args.plasma_file):
        # the YAML runs this step only when the pre-upgrade run should have made the snapshot
        if str(args.skip_if_missing).lower() != "true":
            raise SystemExit(f"{args.plasma_file} not found: the pre-upgrade plasma capture did not run or failed")
        log.info(f"{args.plasma_file} not found: this run made no plasma holes before the upgrade, nothing to validate")
        return
    snapshot = load_snapshot(args.plasma_file)
    before = snapshot["collections"]
    log.info(f"Snapshot from {snapshot['captured_at']} on {snapshot['cluster_versions']}, cluster now {cluster.versions()}")
    current = plasma_by_collection(load_stats(args.stats_after)["instances"])
    print_plasma("before the upgrade", before)
    print_plasma("after the upgrade", current)
    for name, was in before.items():
        is_now = current.get(name)
        if not is_now or not is_now["instances"]:
            checks.fail(f"{name}: no index instances after the upgrade (before: {was['instances']})")
        elif is_now["items"] != was["items"]:
            checks.fail(f"{name}: {is_now['items']} indexed items after the upgrade, {was['items']} before")
        elif is_now["instances"] != was["instances"]:
            checks.warn(f"{name}: {is_now['instances']} index instances after the upgrade, {was['instances']} before")

    for path in [f for f in (args.stats_timeline or "").split(",") if f]:
        for entry in load_stats(path)["timeline"]:
            total = plasma_grand_total(plasma_by_collection(entry["instances"]))
            log.info(f"[{os.path.basename(path)} {entry['at']}] {total['pages']} pages, {total['density']} items/page, "
                     f"{total['empty_pages']} empty pages, {total['purges']} purges, {total['merged_empty']} merged")

    final_stats = load_stats(args.stats_final)
    final = plasma_by_collection(final_stats["instances"])
    print_plasma("end of the check", final)
    watch = final_stats.get("timeline") or []
    watch_note = ""
    if len(watch) >= 2:
        first_empty = plasma_grand_total(plasma_by_collection(watch[0]["instances"]))["empty_pages"]
        last_empty = plasma_grand_total(plasma_by_collection(watch[-1]["instances"]))["empty_pages"]
        minutes = round((datetime.fromisoformat(watch[-1]["at"].rstrip("Z")) -
                         datetime.fromisoformat(watch[0]["at"].rstrip("Z"))).total_seconds() / 60)
        trend = "fell" if last_empty < first_empty else "did not fall"
        watch_note = f"; during the last {minutes}-minute watch they {trend}: {first_empty} -> {last_empty}"
        log.info(f"final watch: {len(watch)} reads over {minutes} minutes, empty pages {first_empty} -> {last_empty}")
    grand_before, grand_end = plasma_grand_total(before), plasma_grand_total(final)
    if not grand_end["hole_stats"]:
        checks.warn("this indexer does not report empty pages (before 7.6.9): the empty-page checks were skipped")
    else:
        was_empty = grand_before["empty_pages"]
        if grand_end["empty_pages"] > 0 and grand_end["empty_pages"] >= was_empty > 0:
            (checks.fail if str(args.plasma_fail_on_empty).lower() == "true" else checks.warn)(
                f"{grand_end['empty_pages']} empty pages left after the watch, scans, writes and the final watch "
                f"(before the upgrade: {was_empty}){watch_note}")
        if was_empty and not grand_end["merged_empty"] and not grand_end["hf_holes"]:
            checks.warn("no empty page merges and no hole-finder activity were recorded")
    if grand_before["density"] and grand_end["density"] and grand_end["density"] < grand_before["density"] * 0.5:
        checks.warn(f"live items per page fell from {grand_before['density']} to {grand_end['density']}")
    checks.report()


# ------------------------------------------------------------------ BHIVE churn and recall: the checks
# BHIVE indexes are Magma-backed: /stats/storage has no num_pages / empty page stats for them, but item_count,
# approx_total_records, total_data_size and purge_ratio.

def bhive_totals(instances):
    """Per collection: instances, indexed items (the same on every replica: the max), records, data size, purge ratio."""
    groups = {}
    for key, stats in instances.items():
        groups.setdefault(key.split("|")[1].split(":")[2], []).append(stats)
    return {name: {"instances": len(rows), "items": max(r.get("item_count") or 0 for r in rows),
                   "records": max(r.get("approx_total_records") or 0 for r in rows),
                   "data_size": sum(r.get("total_data_size") or 0 for r in rows),
                   "purge_ratio": max(r.get("purge_ratio") or 0 for r in rows)}
            for name, rows in sorted(groups.items())}


def print_bhive(title, totals):
    rows = [[name, t["instances"], t["items"], t["records"], t["data_size"], t["purge_ratio"]] for name, t in totals.items()]
    print_table([title, "instances", "items", "records", "data size", "purge ratio"], rows)


def capture_bhive_state(cluster, args):
    """Before the upgrade, after the reload and the drain wait (indexmanager report_storage_stats wrote --stats_file): check
    both collections hold --bhive_docs indexed items again and keep the per-collection totals for validate_bhive."""
    checks = Checks("capture_bhive_state")
    instances = load_stats(args.stats_file)["instances"]
    totals = bhive_totals(instances)
    if not totals:
        raise SystemExit(f"no BHIVE index instances of {BHIVE_BUCKET} in {args.stats_file}")
    print_bhive("pre-upgrade", totals)
    for name in BHIVE_COLLECTIONS:
        if name not in totals:
            checks.fail(f"{name}: no BHIVE index instances")
        elif totals[name]["items"] != args.bhive_docs:
            checks.fail(f"{name}: {totals[name]['items']} indexed items, expected {args.bhive_docs}")
    _write_json_atomic(args.bhive_file, {"captured_at": datetime.utcnow().isoformat() + "Z",
                                         "cluster_versions": cluster.versions(), "collections": totals})
    checks.report()


def validate_bhive(cluster, args):
    """After the upgrade, against capture_bhive_state, from the files indexmanager report_storage_stats wrote: --stats_after
    (right after the upgrade), --stats_timeline (reads over the settle window) and --stats_final (after the light writes
    and the drain wait, which is wait_until_mutations_processed). The same indexed items; a final data size that has not grown
    beyond --bhive_size_growth times the pre-upgrade one is a warning. Recall is compared by compare_recall."""
    checks = Checks("validate_bhive")
    if not os.path.exists(args.bhive_file):
        # the YAML runs this step only when the pre-upgrade run should have made the snapshot
        if str(args.skip_if_missing).lower() != "true":
            raise SystemExit(f"{args.bhive_file} not found: the pre-upgrade BHIVE capture did not run or failed")
        log.info(f"{args.bhive_file} not found: this run did not churn BHIVE indexes before the upgrade (source before 8.0)")
        return
    with open(args.bhive_file) as f:
        before = json.load(f)["collections"]
    now = bhive_totals(load_stats(args.stats_after)["instances"])
    print_bhive("before the upgrade", before)
    print_bhive("after the upgrade", now)
    for name, was in before.items():
        is_now = now.get(name)
        if not is_now:
            checks.fail(f"{name}: no BHIVE index instances after the upgrade")
        elif is_now["items"] != was["items"]:
            checks.fail(f"{name}: {is_now['items']} indexed items after the upgrade, {was['items']} before")
        elif is_now["instances"] != was["instances"]:
            checks.warn(f"{name}: {is_now['instances']} BHIVE instances after the upgrade, {was['instances']} before")
    for path in [f for f in (args.stats_timeline or "").split(",") if f]:
        for entry in load_stats(path)["timeline"]:
            sizes = {n: (t["data_size"], t["purge_ratio"]) for n, t in bhive_totals(entry["instances"]).items()}
            log.info(f"[{os.path.basename(path)} {entry['at']}] (data size, purge ratio) {sizes}")
    final = bhive_totals(load_stats(args.stats_final)["instances"])
    print_bhive("end of the check", final)
    for name, was in before.items():
        end = final.get(name)
        if end and was["data_size"] and end["data_size"] > was["data_size"] * args.bhive_size_growth:
            checks.warn(f"{name}: data size {was['data_size']} -> {end['data_size']} "
                        f"(more than {args.bhive_size_growth}x): space not reclaimed")
        if end and end["items"] != was["items"]:
            checks.fail(f"{name}: {end['items']} indexed items at the end, {was['items']} before the upgrade")
    checks.report()


def cluster_state(cluster, args):
    """A snapshot of the cluster for troubleshooting a later reading (for example a recall that dropped): when it was taken,
    every node with its version, services and state, the rebalance status, the number of GSI indexes per bucket and state,
    and for the indexes of --state_buckets (default: every bucket with an index) the indexer's own status, from
    GET :9102/getIndexStatus on the index nodes (state, build progress, replicas, partitions, pending docs where reported).
    Written to --state_file (JSON, label + time inside) and summarised in the log."""
    taken = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    pool = cluster.mgmt("GET", "/pools/default").json()
    nodes = [{"hostname": n.get("hostname"), "version": n.get("version"), "services": n.get("services"),
              "status": n.get("status"), "membership": n.get("clusterMembership"),
              "uptime_s": n.get("uptime"), "mem_total": (n.get("systemStats") or {}).get("mem_total"),
              "mem_free": (n.get("systemStats") or {}).get("mem_free")} for n in pool.get("nodes", [])]
    rebalance = cluster.mgmt("GET", "/pools/default/rebalanceProgress").json().get("status")
    print_table(["node", "version", "services", "status", "membership"],
                [[n["hostname"], n["version"], ",".join(n["services"] or []), n["status"], n["membership"]] for n in nodes])
    log.info(f"[cluster_state:{args.state_label}] {taken}, rebalance {rebalance}, {len(nodes)} nodes")
    states = cluster.index_states()
    per_bucket = {}
    for (bucket, _scope, _coll, _name), state in states.items():
        per_bucket.setdefault(bucket, {}).setdefault(state, 0)
        per_bucket[bucket][state] += 1
    print_table(["bucket", "indexes by state"], [[b, json.dumps(v, sort_keys=True)] for b, v in sorted(per_bucket.items())])
    wanted = {b.strip() for b in (args.state_buckets or "").split(",") if b.strip()} or set(per_bucket)
    keep = ("indexName", "bucket", "scope", "collection", "status", "progress", "replicaId", "numReplica", "numPartition",
            "partitioned", "hosts", "lastScanTime", "numDocsPending", "numDocsQueued", "completion", "stale")
    details = []
    for node in nodes:
        if "index" not in (node["services"] or []):
            continue
        host = (node["hostname"] or "").rsplit(":", 1)[0].strip("[]")
        try:
            response = requests.get(f"{cluster.scheme}://{host}:{9102 if cluster.scheme == 'http' else 19102}/getIndexStatus",
                                    auth=cluster.auth, timeout=120, verify=False)
            for index in response.json().get("status", []):
                if index.get("bucket") in wanted:
                    details.append({"from_node": host, **{k: index[k] for k in keep if k in index}})
            break       # every index node reports the whole cluster: one answer is enough
        except (requests.exceptions.RequestException, ValueError) as e:
            log.warning(f"[cluster_state:{args.state_label}] getIndexStatus on {host} failed: {e}")
    log.info(f"[cluster_state:{args.state_label}] indexer status of {len(details)} index instances in {sorted(wanted)}")
    not_ready = [d for d in details if d.get("status") != "Ready"]
    if not_ready:
        log.warning(f"[cluster_state:{args.state_label}] {len(not_ready)} index instances not Ready: "
                    f"{[(d['indexName'], d['status'], d.get('progress')) for d in not_ready][:20]}")
    if args.state_file:
        _write_json_atomic(args.state_file, {"label": args.state_label, "taken_at": taken, "nodes": nodes,
                                             "rebalance": rebalance, "indexes_by_bucket_state": per_bucket,
                                             "index_instances": details})
        log.info(f"[cluster_state:{args.state_label}] written to {args.state_file}")


def describe_recall_readings(readings, checks):
    """Troubleshooting detail for the recall readings, from what query_manager --recall_file records per execution:
    when each ran and with which parameters, how the recall spreads over the query templates, and every execution under 50%
    (a failed query counts as recall 0 in the mean, so the error and the result count say which it was). A few
    executions per reading are random draws of query vector, keyspace and scan consistency: the table shows the sample, so
    a mean built on 16 draws is not mistaken for a trend."""
    for label, data in readings:
        params = data.get("params") or {}
        executions = data.get("executions") or []
        log.info(f"[recall:{label}] ran {data.get('started_at', '?')} .. {data.get('ended_at', '?')}, {data.get('queries')} queries, "
                 f"mean {data.get('mean_recall', 0):.2f}, params {json.dumps(params, sort_keys=True)}")
        if not executions:
            log.info(f"[recall:{label}] no per-execution records in this file (written by an older query_manager)")
            continue
        errors = [e for e in executions if e.get("error")]
        consistency = {}
        for e in executions:
            consistency[e.get("scan_consistency")] = consistency.get(e.get("scan_consistency"), 0) + 1
        log.info(f"[recall:{label}] {len(executions)} executions: {len(errors)} with an error, scan consistency {consistency}, "
                 f"distinct query vectors {len({e.get('query_vector_index') for e in executions})}")
        by_template = {}
        for e in executions:
            by_template.setdefault((e.get("query_id") or "?").split("#")[0], []).append(e["recall"])
        print_table([f"{label}: query template", "executions", "mean recall %", "min", "max"],
                    [[name, len(v), round(sum(v) / len(v), 1), min(v), max(v)] for name, v in sorted(by_template.items())])
        low = sorted((e for e in executions if e["recall"] < 50), key=lambda e: e["at"])
        if low:
            print_table([f"{label}: recall < 50", "at", "recall", "results", "retry rows", "keyspace", "vector", "consistency",
                         "elapsed s", "error / warnings"],
                        [[e.get("query_id"), e["at"][11:23], e["recall"], e.get("result_count"), e.get("retry_result_count", "-"),
                          e.get("keyspace"), e.get("query_vector_index"), e.get("scan_consistency"), e.get("elapsed_s"),
                          ((e.get("error") or "") + " ".join(e.get("warnings") or []))[:70]] for e in low])
    for (first, a), (second, b) in zip(readings, readings[1:]):
        pa, pb = a.get("params") or {}, b.get("params") or {}
        for key in sorted(set(pa) | set(pb)):
            if key in ("connection_string",):
                continue
            if pa.get(key) != pb.get(key):
                checks.warn(f"{first} and {second} ran with different {key}: {pa.get(key)} vs {pb.get(key)}")
        if abs(a["queries"] - b["queries"]) > max(2, 0.2 * a["queries"]):
            checks.warn(f"{first} has {a['queries']} queries, {second} has {b['queries']}: the means are over different samples")


def compare_recall(cluster, args):
    """Recall readings from query_manager --recall_file, in order (label=path,label=path,...): a mean recall that
    falls from one reading to the next by more than --recall_warn_drop points warns, by more than --recall_fail_drop
    fails. A missing file fails (the YAML gates this step like the steps that write the files, so a missing one means
    the reading did not complete); --skip_if_missing true skips it instead. The readings must also be in time order: /data
    persists across runs, so a reading that started before the previous one ended is a leftover from an earlier run."""
    checks = Checks("compare_recall")
    readings = []
    for item in [i for i in (args.recall_files or "").split(",") if i]:
        label, _, path = item.partition("=")
        if not os.path.exists(path):
            if str(args.skip_if_missing).lower() == "true":
                log.info(f"{path} not found: {label} skipped")
            else:
                checks.fail(f"{label}: {path} not found")
            continue
        with open(path) as f:
            data = json.load(f)
        if not data.get("queries"):
            checks.fail(f"{label}: no recall measured (0 queries in {path})")
            continue
        readings.append((label, data))
    for (first, a), (second, b) in zip(readings, readings[1:]):
        try:
            stale = datetime.fromisoformat(b["started_at"]) < datetime.fromisoformat(a["ended_at"])
        except (KeyError, TypeError, ValueError):
            checks.warn(f"{first} / {second}: no started_at / ended_at, cannot tell whether {second} is from this run")
            continue
        if stale:
            checks.fail(f"{second} started {b['started_at']}, before {first} ended {a['ended_at']}: "
                        f"{second} is a leftover from an earlier run")
    rows = []
    for label, data in readings:
        total = data["queries"]
        low = sum(v for k, v in data["histogram"].items() if int(k) < 7)
        rows.append([label, total, round(data["mean_recall"], 2), round(100 * low / total, 1)])
    print_table(["reading", "queries", "mean recall %", "% of queries below 70"], rows)
    describe_recall_readings(readings, checks)
    for (first, a), (second, b) in zip(readings, readings[1:]):
        drop = a["mean_recall"] - b["mean_recall"]
        message = f"mean recall {a['mean_recall']:.2f} ({first}) -> {b['mean_recall']:.2f} ({second})"
        if drop > args.recall_fail_drop:
            checks.fail(message)
        elif drop > args.recall_warn_drop:
            checks.warn(message)
    checks.report()



# ------------------------------------------------------------------ rebalance

def wait_for_rebalance(cluster, host, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = cluster.mgmt("GET", "/pools/default/rebalanceProgress", host=host).json()
        if status.get("status") == "none":
            tasks = cluster.mgmt("GET", "/pools/default/tasks", host=host).json()
            errors = [t.get("errorMessage") for t in tasks if t.get("type") == "rebalance" and t.get("errorMessage")]
            if errors:
                raise SystemExit(f"rebalance failed: {errors}")
            return
        progress = {k: round(v.get("progress", 0) * 100) for k, v in status.items() if isinstance(v, dict)}
        log.info(f"rebalance running: {progress}")
        time.sleep(30)
    raise SystemExit(f"rebalance did not finish within {timeout}s")


def member(cluster, ip, host=None):
    for node in cluster.mgmt("GET", "/pools/default", host=host).json().get("nodes", []):
        if node["hostname"].rsplit(":", 1)[0].strip("[]") == ip:
            return node
    return None


REBALANCE_WINDOWS_FILE = "/data/gsi_query_upgrade_rebalance_windows.json"


def record_rebalance_window(started, ended, ejected, ok):
    """Append {start, end (UTC), ejected, ok} to REBALANCE_WINDOWS_FILE: suite_report compares the query errors of
    run_suite with these windows to say which errors happened while a rebalance was running."""
    try:
        windows = []
        if os.path.exists(REBALANCE_WINDOWS_FILE):
            with open(REBALANCE_WINDOWS_FILE) as f:
                windows = json.load(f)
        windows.append({"start": started, "end": ended, "ejected": list(ejected), "ok": ok})
        _write_json_atomic(REBALANCE_WINDOWS_FILE, windows)
    except (OSError, ValueError) as e:
        log.warning(f"rebalance window not recorded: {e}")


def rebalance(cluster, host, ejected, timeout):
    started = datetime.utcnow().isoformat(timespec="seconds")
    ok = False
    try:
        _rebalance(cluster, host, ejected, timeout)
        ok = True
    finally:
        record_rebalance_window(started, datetime.utcnow().isoformat(timespec="seconds"), ejected, ok)


def _rebalance(cluster, host, ejected, timeout):
    known = ",".join(n["otpNode"] for n in cluster.mgmt("GET", "/pools/default", host=host).json()["nodes"])
    response = cluster.mgmt("POST", "/controller/rebalance", host=host,
                            data={"knownNodes": known, "ejectedNodes": ",".join(ejected)})
    if response.status_code != 200:
        raise SystemExit(f"starting rebalance failed: {response.status_code} {response.text}")
    time.sleep(10)
    wait_for_rebalance(cluster, host, timeout)


def node_paths(cluster, host):
    hdd = cluster.mgmt("GET", "/nodes/self", host=host).json()["storage"]["hdd"][0]
    return hdd["path"], hdd["index_path"]


def wait_for_indexes(cluster, args):
    """Wait until every GSI index is Ready again. An offline (in-place) upgrade restarts every indexer, which recovers
    its indexes from disk (warmup) before it serves scans; an online upgrade's swap rebalances already wait for that."""
    checks = Checks("wait_for_indexes")
    deadline = time.time() + args.timeout
    while True:
        pending = None
        try:
            response = cluster.mgmt("GET", "/indexStatus")
            response.raise_for_status()
            indexes = response.json().get("indexes", [])
            pending = [f"{i.get('index')}({i.get('status')})" for i in indexes if i.get("status") != "Ready"]
            if not pending:
                # -n may be a node without the query service (e.g. the KV-only orchestrator)
                states = cluster.index_states(host=cluster.query_nodes()[0])
                pending = [f"{k[-1]}({v})" for k, v in states.items() if v != "online"]
        except (requests.exceptions.RequestException, ValueError, SystemExit) as e:
            pending = [f"index status not readable: {e}"]
        if not pending:
            log.info(f"All {len(indexes)} index instances Ready")
            break
        if time.time() > deadline:
            checks.fail(f"{len(pending)} index instances not Ready after {args.timeout}s: {pending[:20]}")
            break
        log.info(f"Waiting for {len(pending)} index instances: {pending[:10]}")
        time.sleep(30)
    checks.report()


def rebalance_in(cluster, args):
    node = args.node.split(":")[0]
    if member(cluster, node):
        raise SystemExit(f"{node} is already in the cluster")
    # A freshly installed node keeps the default paths under /opt (root disk) unless initialized: copy the
    # data/index paths of a node already running the same service (what couchbase-cli node-init does)
    services = set(args.services.split(","))
    reference = next((n["hostname"].rsplit(":", 1)[0] for n in cluster.nodes()
                      if n.get("clusterMembership") == "active" and services & set(n.get("services", []))),
                     cluster.host)
    data_path, index_path = node_paths(cluster, reference)
    response = cluster.mgmt("POST", "/nodes/self/controller/settings", host=node,
                            data={"path": data_path, "index_path": index_path})
    if response.status_code != 200 or node_paths(cluster, node) != (data_path, index_path):
        raise SystemExit(f"setting data/index paths {data_path} / {index_path} on {node} failed: "
                         f"{response.status_code} {response.text}")
    log.info(f"{node} data path {data_path}, index path {index_path} (from {reference})")
    hostname = f"https://{node}" if args.add_node_scheme == "https" else node
    response = cluster.mgmt("POST", "/controller/addNode",
                            data={"hostname": hostname, "user": cluster.username, "password": cluster.password,
                                  "services": args.services})
    if response.status_code != 200:
        raise SystemExit(f"addNode {node} failed: {response.status_code} {response.text}")
    rebalance(cluster, cluster.host, [], args.timeout)
    added = member(cluster, node)
    if not added or added.get("clusterMembership") != "active":
        raise SystemExit(f"{node} is not an active member after rebalance-in")
    log.info(f"{node} rebalanced in with services {added.get('services')} ({added.get('version')})")


def rebalance_out(cluster, args):
    node = args.node.split(":")[0]
    target = member(cluster, node)
    if not target:
        raise SystemExit(f"{node} is not in the cluster")
    host = cluster.host if cluster.host != node else next(
        n["hostname"].rsplit(":", 1)[0] for n in cluster.nodes() if n["hostname"].rsplit(":", 1)[0] != node)
    rebalance(cluster, host, [target["otpNode"]], args.timeout)
    if member(cluster, node, host=host):
        raise SystemExit(f"{node} is still in the cluster after rebalance-out")
    log.info(f"{node} rebalanced out")


ACTIONS = {
    "wait_for_docs": wait_for_docs,
    "require_indexes": require_indexes,
    "cluster_state": cluster_state,
    "prepareds_state": prepareds_state,
    "completed_requests": completed_requests,
    "apply_index_spec": apply_index_spec,
    "disable_sequential_scans": disable_sequential_scans,
    "update_statistics": update_statistics,
    "create_udfs": create_udfs,
    "capture_baseline": capture_baseline,
    "wait_for_indexes": wait_for_indexes,
    "validate_statistics": validate_statistics,
    "validate_baseline": validate_baseline,
    "run_suite": run_suite,
    "suite_report": suite_report,
    "run_ddl": run_ddl,
    "ddl_report": ddl_report,
    "capture_plasma_state": capture_plasma_state,
    "plasma_scans": plasma_scans,
    "validate_plasma": validate_plasma,
    "capture_bhive_state": capture_bhive_state,
    "validate_bhive": validate_bhive,
    "compare_recall": compare_recall,
    "rebalance_in": rebalance_in,
    "rebalance_out": rebalance_out,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-n", "--host", required=True, help="cluster node (a query node for query actions)")
    parser.add_argument("-u", "--username", default="Administrator")
    parser.add_argument("-p", "--password", default="password")
    parser.add_argument("-a", "--action", required=True, choices=sorted(ACTIONS))
    parser.add_argument("--tls", default="false")
    parser.add_argument("--spec", default="/index_spec.yml")
    parser.add_argument("--suite", default="/query_suite.yml")
    parser.add_argument("--snapshot_file", default="/data/gsi_query_upgrade_baseline.json")
    parser.add_argument("--timeout", type=int, default=7200, help="index build / rebalance timeout (s)")
    parser.add_argument("--expected_docs", help="wait_for_docs: 'bucket.scope.coll=N,...'")
    parser.add_argument("--expected_indexes", help="require_indexes: 'bucket.scope.coll=index_name,...'")
    parser.add_argument("--docs_at_most", default="false", help="wait_for_docs: wait for the counts to fall to N or below")
    parser.add_argument("--state_label", default="state", help="cluster_state: label of the snapshot, for the log and the file")
    parser.add_argument("--cr_mode", default="report", help="completed_requests: start | stop | report")
    parser.add_argument("--cr_state_file", default="/data/gsi_query_upgrade_completed_requests_state.json")
    parser.add_argument("--cr_report_file", default="/data/gsi_query_upgrade_completed_requests_report.json")
    parser.add_argument("--cr_limit", type=int, default=50000, help="completed_requests start: queryCompletedLimit during the window")
    parser.add_argument("--previous_file", default=None,
                        help="prepareds_state: the snapshot taken before the upgrade, to print what disappeared since")
    parser.add_argument("--state_file", default=None, help="cluster_state: JSON file to write (a volume such as /data)")
    parser.add_argument("--state_buckets", default="", help="cluster_state: comma separated buckets whose indexer status is kept")
    parser.add_argument("--max_concurrent_builds", type=int, default=16,
                        help="apply_index_spec: max index instances (replicas included) building at once")
    parser.add_argument("--stats_timeout", type=int, default=900, help="UPDATE STATISTICS timeout (s)")
    parser.add_argument("--runs", type=int, default=3, help="timed runs per query (after one warm-up)")
    parser.add_argument("--latency_ceiling", type=float, default=3.0)
    parser.add_argument("--fail_on_plan_change", default="true")
    parser.add_argument("--expect_prepared_survive", default="auto", choices=["auto", "true", "false"],
                        help="validate_baseline: fail when prepared statements are lost by the upgrade "
                             "(auto: only when some query node kept them, i.e. not a restart of every query node)")
    parser.add_argument("--upgrade_mode", default="", help="validate_baseline: online or offline (upgrade.sh upgrades "
                        "one node at a time in both) makes --expect_prepared_survive auto strict; empty keeps auto")
    parser.add_argument("--duration", type=int, default=3600, help="run_suite / run_ddl duration (s)")
    parser.add_argument("--ddl_file", default="/data/gsi_query_upgrade_ddl_run.json",
                        help="run_ddl progress file, read by ddl_report")
    parser.add_argument("--ddl_pause", type=int, default=30, help="run_ddl: seconds between DDL rounds")
    parser.add_argument("--stats_file", default=None,
                        help="capture_*_state: the indexmanager report_storage_stats file to capture")
    parser.add_argument("--stats_after", default=None, help="validate_*: report_storage_stats file right after the upgrade")
    parser.add_argument("--stats_timeline", default=None,
                        help="validate_*: comma separated report_storage_stats files of reads over time, in order")
    parser.add_argument("--stats_final", default=None, help="validate_*: report_storage_stats file at the end of the check")
    parser.add_argument("--plasma_file", default="/data/gsi_query_upgrade_plasma.json",
                        help="capture_plasma_state snapshot, read by validate_plasma")
    parser.add_argument("--plasma_fail_on_empty", default="false",
                        help="validate_plasma: fail (not warn) when empty pages are not merged (true / false)")
    parser.add_argument("--plasma_bloat_density", type=float, default=100.0,
                        help="capture_plasma_state: warn if a collection still has more live items per page than this")
    parser.add_argument("--bhive_docs", type=int, default=1000000,
                        help="capture_bhive_state: docs per collection (1M: the groundtruth idx_1M.ivecs only fits the full set)")
    parser.add_argument("--bhive_file", default="/data/gsi_query_upgrade_bhive.json",
                        help="capture_bhive_state snapshot, read by validate_bhive")
    parser.add_argument("--bhive_size_growth", type=float, default=1.5,
                        help="validate_bhive: warn when the data size grew beyond this factor of the pre-upgrade size")
    parser.add_argument("--recall_files", default=None, help="compare_recall: label=path,label=path in reading order")
    parser.add_argument("--recall_warn_drop", type=float, default=2.0, help="compare_recall: mean recall points that warn")
    parser.add_argument("--recall_fail_drop", type=float, default=10.0, help="compare_recall: mean recall points that fail")
    parser.add_argument("--skip_if_missing", default="false", help="compare_recall / validate_plasma / validate_bhive: skip a missing input file instead of failing")
    parser.add_argument("--fail_on_query_error", default="true",
                        help="suite_report: fail on query errors seen by run_suite (mismatches always fail)")
    parser.add_argument("--node", help="node for rebalance_in / rebalance_out")
    parser.add_argument("--services", default="index", help="services for rebalance_in")
    parser.add_argument("--add_node_scheme", default="https", choices=["http", "https"])
    args = parser.parse_args()
    args.fail_on_plan_change = args.fail_on_plan_change.lower() == "true"
    # Both upgrade.sh modes restart one query node at a time, which primes its cache from a peer
    if args.expect_prepared_survive == "auto" and args.upgrade_mode.lower() in ("online", "offline"):
        args.expect_prepared_survive = "true"
    args.fail_on_query_error = args.fail_on_query_error.lower() == "true"
    args.docs_at_most = str(args.docs_at_most).lower() == "true"

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    cluster = Cluster(args.host, args.username, args.password, tls=args.tls.lower() == "true")
    ACTIONS[args.action](cluster, args)


if __name__ == "__main__":
    main()

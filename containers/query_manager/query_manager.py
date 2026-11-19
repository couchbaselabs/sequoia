import argparse
import faulthandler
import logging
import time
import random
import json
import os
import re
import sys
import uuid
from dns import resolver
import struct
import requests
import numpy as np
from beautifultable import BeautifulTable
from deepdiff import DeepDiff
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster
from couchbase.options import (ClusterOptions,
                               QueryOptions, AnalyticsOptions)
from couchbase.exceptions import CouchbaseException
from couchbase.cluster import QueryScanConsistency
import threading

# Long numeric list literals (dense query vectors, sparse indices/values) substituted into statements.
VECTOR_LITERAL_RE = re.compile(r"\[[-+0-9.eE,\s]{80,}\]")
# Distinct messages / ids kept per failure group so the summary stays bounded on long runs.
MAX_SAMPLES_PER_FAILURE_GROUP = 3


class QueryManager:
    def __init__(self, connection_string, username, password, timeout, duration, doc_template, use_sdk, query_type,
                 query_file, groundtruth_file, validate_vector_query_results, distance_algo, bucket_list, use_tls,
                 capella="false", skip_default="false", num_groundtruth_vectors=100, num_query_vectors=10000,
                 base64_encoding="false", xattrs="false", sample_size=20, bhive_queries=False, print_frequency=30,
                 log_level="INFO", smoke_test_run="false", enable_scan_report="false", nprobe=None):
        self.connection_string = connection_string
        self.nprobe = nprobe  # fixed nprobe for every vector query (None: derived from the filter / random)
        self.username = username
        self.password = password
        self.cluster = None
        self.timeout = timeout
        self.duration = duration
        self.template = doc_template
        self.use_sdk = use_sdk == "true"
        self.query_type = query_type
        self.query_file = query_file
        self.groundtruth_file = groundtruth_file
        self.validate_vector_query_results = validate_vector_query_results == 'true'
        self.distance_algo = distance_algo
        self.bucket_list = bucket_list
        self.limit_val = random.randint(1, 100)
        self.use_tls = use_tls == "true"
        self.capella = capella == "true"
        self.skip_default = skip_default == "true"
        self.num_groundtruth_vectors = num_groundtruth_vectors
        self.num_query_vectors = num_query_vectors
        self.base64_encoding = base64_encoding == "true"
        self.xattrs = xattrs == "true"
        self.sample_size = sample_size
        self.bhive_queries = bhive_queries == "true"
        self.enable_scan_report = enable_scan_report == "true"
        self.smoke_test_run = smoke_test_run == "true"
        # generated statement -> {"query_id": "<template>#<n>", "keyspace": "b.s.c"}
        self.query_catalog = {}
        # failure group key -> aggregated failure info, see record_query_failure()
        self.query_failure_groups = {}
        # (query_id, keyspace) -> number of executions attempted
        self.query_exec_counts = {}
        self._failures_lock = threading.Lock()
        self.print_frequency = print_frequency
        self.log = logging.getLogger("query_manager")
        # Set log level based on parameter
        log_level = getattr(logging, log_level.upper(), logging.INFO)
        self.log.setLevel(log_level)
        ch = logging.StreamHandler()
        # sparse (msmarco) recall: the .gt files hold the unfiltered top-10 per query (0-based row ids), keys are <prefix>-<row>
        self.sparse_recall = self.validate_vector_query_results and "sparse" in self.template
        self.sparse_id_offset = 0
        self.sparse_limit = 10
        self.dense_topn = None  # topNScan for dense BHIVE queries (6th argument of APPROX_VECTOR_DISTANCE); None = not passed
        self.sparse_topn = None  # topNScan, 4th argument of SPARSE_VECTOR_DISTANCE; None = server default
        self.keyspace_list = None  # explicit keyspaces (bucket.scope.collection), overrides discovery
        # MS MARCO qrels per query-vector row (list of relevant passage ids), for IR-style recall; None = not measured
        self.qrels = None
        self.qrels_sum = 0.0
        self.qrels_queries = 0
        self.recall_dict = dict()
        self.recall_sum = 0
        self.recall_queries = 0
        # one record per recall execution (see compute_recall), written to the recall file for troubleshooting
        self.recall_executions = []
        self.recall_started_at = datetime.now().isoformat(timespec="seconds")
        ch.setLevel(log_level)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        ch.setFormatter(formatter)
        self.log.addHandler(ch)
        timestamp = str(datetime.now().strftime('%Y%m%dT_%H%M%S'))
        fh = logging.FileHandler("./query_manager-{0}.log".format(timestamp))
        fh.setFormatter(formatter)
        self.log.addHandler(fh)
        self.log.info("Query manager started")

    def get_recall_dict(self):
        return self.recall_dict

    def update_recall_dict(self, recall_percentage):
        # Calculate which range (0-10, 10-20, etc) this percentage falls into
        range_index = recall_percentage // 10
        if range_index in self.recall_dict:
            self.recall_dict[range_index] += 1
        else:
            self.recall_dict[range_index] = 1
        self.recall_sum += recall_percentage
        self.recall_queries += 1
        return

    def write_recall_file(self, path, params=None):
        """Recall of this run as JSON (histogram by 10% bucket, query count, mean recall) so a later step can compare
        runs, for example before and after an upgrade. Written atomically."""
        mean = self.recall_sum / self.recall_queries if self.recall_queries else None
        data = {"histogram": {str(k): v for k, v in sorted(self.recall_dict.items())}, "queries": self.recall_queries,
                "mean_recall": mean, "template": self.template,
                "qrels_recall_mean": (100 * self.qrels_sum / self.qrels_queries) if self.qrels_queries else None,
                "qrels_queries": self.qrels_queries,
                "started_at": self.recall_started_at, "ended_at": datetime.now().isoformat(timespec="seconds"),
                "params": params or {}, "executions": list(self.recall_executions)}
        tmp = f"{path}.tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
        self.log.info(f"Recall written to {path}: {self.recall_queries} queries, mean recall {mean}")

    def create_cluster_object(self):
        auth = PasswordAuthenticator(self.username, self.password)
        options = ClusterOptions(auth)
        options.apply_profile('wan_development')
        if self.use_tls or self.capella:
            self.cluster = Cluster(f"couchbases://{self.connection_string}?tls_verify=none",
                                   options)
        else:
            self.cluster = Cluster(f"couchbase://{self.connection_string}?tls_verify=none",
                                   options)

    def fetch_rest_url(self):
        srv_info = {}
        srv_records = resolver.resolve('_couchbases._tcp.' + self.connection_string, 'SRV')
        for srv in srv_records:
            srv_info['host'] = str(srv.target).rstrip('.')
            srv_info['port'] = srv.port
        return srv_info['host']

    def get_all_buckets(self):
        query = "Select * from system:buckets"
        results = self.run_n1ql_query(query, True)
        self.log.info(f"Results from system:buckets {results}")
        bucket_list = []
        for item in results:
            bucket_list.append(item['buckets']['name'])
        return bucket_list

    def fetch_keyspaces_list(self):
        keyspaces = []
        if self.keyspace_list:
            return [k.strip() for k in self.keyspace_list.split(",") if k.strip()]
        self.create_cluster_object()
        if self.query_type == 'analytics':
            query = """select value ds.DatabaseName || "." || ds.DataverseName || "." || ds.DatasetName 
            from Metadata.`Dataset` as ds where ds.DataverseName <> \"Metadata\""""
            results = self.run_analytics_query(query)
            if self.use_sdk:
                keyspaces = [row for row in results.rows()]
            else:
                keyspaces = results
        else:
            if self.bucket_list:
                bucket_list = self.bucket_list.split(",")
            else:
                bucket_list = self.get_all_buckets()
            for bucket_name in bucket_list:
                bucket_obj = self.cluster.bucket(bucket_name)
                scopes = bucket_obj.collections().get_all_scopes()
                self.log.debug("Bucket name {}".format(bucket_name))
                for scope in scopes:
                    if "scope_" in scope.name or "_default" in scope.name:
                        for coll in scope.collections:
                            if "coll_" in coll.name or ("_default" in coll.name and not self.skip_default):
                                keyspaces.append(bucket_name + "." + scope.name + "." + coll.name)
        return keyspaces

    def run_analytics_query(self, query, iterate_over_results=False):
        if not self.cluster and self.use_sdk:
            self.create_cluster_object()
            self.log.info(f"Will run the query {query}")
            try:
                result = self.cluster.analytics_query(query, AnalyticsOptions(timeout=self.timeout))
                if iterate_over_results:
                    result = [row for row in result.rows()]
                    self.log.debug(f"First few rows of the result for the query {query} are {result[:3]}")
                return result
            except:
                self.log.info(f"===========Query {query} has ended in error================================")
        else:
            self.log.info(f"running query - {query} via rest")
            auth = (self.username, self.password)
            payload = {"statement": query}
            api = f"https://" + self.connection_string + ':18095/analytics/service'
            try:
                response = requests.post(url=api, auth=auth, timeout=self.timeout, verify=False,
                                         headers={'Content-Type': 'application/json'}, json=payload)
                if response.status_code == 200:
                    return response.json()['results']
            except:
                pass

    def read_file(self, file_path, end):
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.ivecs':
            return self.read_ivecs(file_path, end)
        elif ext == '.bvecs':
            return self.read_bvecs(file_path, end)
        elif ext == '.fvecs':
            return self.read_fvecs_file(file_path, 0, end)
        elif ext == '.csr':
            return self.read_csr_file(file_path, end)
        elif ext == '.gt':
            return self.read_gt_file(file_path, end)
        raise ValueError(f'Unsupported file format: {file_path}')

    def read_fvecs_file(self, file_path, start, end):
        with open(file_path, 'rb+') as f:
            vectors = {}
            # Read the dimension (4 bytes)
            d_bytes = f.read(4)
            if not d_bytes:
                return vectors
            dim = struct.unpack('i', d_bytes)[0]
            size_of_vectors = 4 + dim * 4
            # Calculate the size of each vector in bytes
            f.seek(start * size_of_vectors)
            data = f.read((end - start) * size_of_vectors)
            for i in range(end - start):
                components_bytes = data[(i * size_of_vectors) + 4:(i + 1) * size_of_vectors]
                components = struct.unpack('f' * dim, components_bytes)
                vectors[i] = list(components)
        return vectors

    @staticmethod
    def _unpack_helper(fmt, dimensions):
        if fmt == '.bvecs':
            return 'B' * dimensions
        elif fmt == '.ivecs':
            return 'i' * dimensions
        elif fmt == '.fvecs':
            return 'f' * dimensions

    def read_ground_truth_file(self, groundtruth_file_path=None):
        if groundtruth_file_path:
            if ".gt" in groundtruth_file_path:
                return self.read_gt_file(groundtruth_file_path, 10000)
            return self.read_file(groundtruth_file_path, 10000)
        if ".gt" in self.groundtruth_file:
            return self.read_gt_file(self.groundtruth_file, self.num_groundtruth_vectors)
        return self.read_file(self.groundtruth_file, self.num_groundtruth_vectors)

    def read_query_file(self):
        if hasattr(self, '_query_vectors_cache'):
            return self._query_vectors_cache

        if 'small' in self.query_file:
            vectors = self.read_fvecs_file(self.query_file, 0, 100)
        elif 'gist' in self.query_file:
            vectors = self.read_fvecs_file(self.query_file, 0, 1000)
        elif 'sift_query' in self.query_file:
            vectors = self.read_fvecs_file(self.query_file, 0, 10000)
        elif '.csr' in self.query_file:
            vectors = self.read_csr_file(self.query_file, self.num_query_vectors)
        else:
            vectors = self.read_file(self.query_file, self.num_query_vectors)

        self._query_vectors_cache = vectors
        return vectors

    def read_ivecs_old(self, fp):
        a = np.fromfile(self.groundtruth_file, dtype='int32')
        d = a[0]
        return a.reshape(-1, d + 1)[:, 1:].copy()

    def read_bvecs(self, filename, num_vectors):
        groundTruths = []
        f = open(filename, '+rb')
        for _ in range(num_vectors):
            # Read the dimension (4 bytes)
            d_bytes = f.read(4)
            dim = struct.unpack('<i', d_bytes)[0]
            vector = f.read(dim)
            components = struct.unpack('<' + ('B' * dim), vector)
            components = list(map(float, components))
            groundTruths.append(components)
        return groundTruths

    def read_ivecs(self, filename, num_vectors):
        gtVectors = []
        f = open(filename, '+rb')
        for _ in range(num_vectors):
            d_bytes = f.read(4)
            dim = struct.unpack('<i', d_bytes)[0]
            vector = f.read(dim * 4)
            components = struct.unpack('<' + 'i' * dim, vector)
            gtVectors.append(components)
        return gtVectors

    def read_csr_file(self, filename, num_vectors):
        """
        Read sparse vectors from custom CSR binary format.
        Format:
            Header: 3 x uint64 (rows, cols, non_zeros)
            indptr: (rows+1) x uint64 (row offsets)
            indices: non_zeros x uint32 (column indices)
            data: non_zeros x float32 (values)
        Returns dict mapping row index -> [[indices], [values]]
        """
        vectors = {}
        with open(filename, 'rb') as f:
            # Read header
            header = struct.unpack('QQQ', f.read(24))
            num_rows, num_cols, num_non_zeros = header
            self.log.debug(f"CSR file: {num_rows} rows, {num_cols} cols, {num_non_zeros} non-zeros")
            # Read indptr (row offsets)
            indptr_size = (num_rows + 1) * 8
            indptr = struct.unpack(f'{num_rows + 1}Q', f.read(indptr_size))
            
            # Store offsets for indices and data sections
            indices_offset = f.tell()
            data_offset = indices_offset + num_non_zeros * 4
            
            # Limit to num_vectors
            rows_to_read = min(num_vectors, num_rows)
            
            for row_idx in range(rows_to_read):
                start = indptr[row_idx]
                end = indptr[row_idx + 1]
                nnz = end - start
                
                # Seek and read indices
                f.seek(indices_offset + start * 4)
                indices = struct.unpack(f'{nnz}I', f.read(nnz * 4))
                
                # Seek and read values
                f.seek(data_offset + start * 4)
                values = struct.unpack(f'{nnz}f', f.read(nnz * 4))
                
                vectors[row_idx] = [list(indices), list(values)]
        
        return vectors

    def read_gt_file(self, filename, num_vectors):
        """
        Read groundtruth from .gt binary format.
        Format:
            first two int32: num_queries, top_k
            remaining data: flattened int32 ids of shape (num_queries, top_k)
        Returns list of tuples/lists containing top_k ids for each query
        """
        gtVectors = []
        with open(filename, 'rb') as f:
            # Read header
            header_bytes = f.read(8)
            if len(header_bytes) != 8:
                raise ValueError(f'GT header truncated: expected 8 bytes, got {len(header_bytes)}')
            num_queries, top_k = struct.unpack('<ii', header_bytes)
            self.log.debug(f"GT file: {num_queries} queries, top_k={top_k}")

            # Limit to num_vectors
            queries_to_read = min(num_vectors, num_queries)
            # Read all groundtruth ids
            total_ids = queries_to_read * top_k
            all_ids = struct.unpack(f'<{total_ids}i', f.read(total_ids * 4))
            
            # Reshape into list of top_k ids per query
            for i in range(queries_to_read):
                start = i * top_k
                gtVectors.append(all_ids[start:start + top_k])
        
        return gtVectors

    def compute_recall(self, groundtruth_vectors, result, index, context=None):
        groundtruth_result_vector = groundtruth_vectors[index]
        query_res_list = [item['id'] for item in result]
        if self.sparse_recall:
            top_k = len(groundtruth_result_vector)
            query_res_list = [int(s.split('-')[-1]) - self.sparse_id_offset for s in query_res_list]
            # exact-neighbour recall: how many of the exact top_k neighbours appear anywhere in the LIMIT results
            # (top_k-recall@LIMIT; with LIMIT == top_k it is plain recall@top_k)
            hits = len(set(groundtruth_result_vector).intersection(query_res_list))
            recall_percentage = hits * 100 // top_k
            self.update_recall_dict(recall_percentage)
            record = {"at": datetime.now().isoformat(timespec="milliseconds"), "recall": recall_percentage,
                      "query_vector_index": index, "result_count": len(query_res_list)}
            if self.qrels is not None and index < len(self.qrels) and self.qrels[index]:
                relevant = set(self.qrels[index])
                qrels_hits = len(relevant.intersection(query_res_list))
                record["qrels_recall"] = round(100 * qrels_hits / len(relevant), 2)
                record["qrels_hits"] = qrels_hits
                record["qrels_relevant"] = len(relevant)
                with self._failures_lock:
                    self.qrels_sum += qrels_hits / len(relevant)
                    self.qrels_queries += 1
            record.update(context or {})
            with self._failures_lock:
                self.recall_executions.append(record)
            if recall_percentage < 50:
                self.log.warning(f"LOW RECALL {recall_percentage}%: {json.dumps(record, default=str)}")
            return
        if 'shoes' not in self.template:
            query_res_list = [int(s.lstrip('doc')) - 1 for s in query_res_list]
            self.log.info(f"Query result {query_res_list}")
        self.log.debug(f"Groundtruth {groundtruth_result_vector[:100]}")
        self.log.debug(f"Query result {query_res_list}")
        recall_percentage = len(list(set(groundtruth_result_vector[:100]).intersection(query_res_list)))
        self.update_recall_dict(recall_percentage)
        record = {"at": datetime.now().isoformat(timespec="milliseconds"), "recall": recall_percentage,
                  "query_vector_index": index, "result_count": len(query_res_list)}
        record.update(context or {})
        with self._failures_lock:
            self.recall_executions.append(record)
        if recall_percentage < 50:
            # a failed or empty query counts as recall 0, so say which it was
            self.log.warning(f"LOW RECALL {recall_percentage}%: {json.dumps(record, default=str)}")

    def calculate_nprobe(self, filter_value):
        """
        Calculate nprobe value based on groundtruth file and filtering ratio
        Returns a value between 50-250 based on the filtering ratio
        """
        # Extract filtering ratio from groundtruth filename
        try:
            # Assuming filename format contains filtering ratio like "1M" or "2M"
            filter_num = filter_value
            total_vectors = int(self.template.split('_')[1].rstrip('M'))
            
            # Calculate filtering ratio (e.g., 1/100, 2/100, etc.)
            filter_ratio = filter_num / total_vectors
            
            # Calculate nprobe based on filtering ratio
            # Using the specified values:
            # 1/100 -> 250
            # 2/100 -> 250
            # 10/100 -> 125
            # 20/100 -> 107
            # 50/100 -> 85
            if filter_ratio <= 0.02:  # 1% or 2%
                return 250
            elif filter_ratio <= 0.1:  # 10%
                return 125
            elif filter_ratio <= 0.2:  # 20%
                return 107
            elif filter_ratio <= 0.5:  # 50%
                return 85
            else:
                return 50  # Default minimum value
        except:
            self.log.warning("Could not parse filtering ratio from groundtruth file, using default nprobe range")
            return random.randint(50, 100)  # Fallback to original behavior
        
    def set_awr_aus(self):
        """Configure AWR and AUS settings for the cluster with fixed scheduling"""
        # Hardcode times to 6 PM to 9 PM IST
        start_time_str = "18:00"  # 6 PM
        end_time_str = "21:00"    # 9 PM
        self.log.info(f"AUS start time: {start_time_str}, AUS end time: {end_time_str}")
        
        # Configure AUS (Automatic Update Statistics)
        aus_query = f"""UPDATE system:aus SET enable = true, change_percentage = 20, all_buckets = true,
        schedule = {{ "start_time": "{start_time_str}", "end_time": "{end_time_str}", "timezone": "Asia/Calcutta", 
        "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] }}"""
        
        # Configure AWR location and interval (using single quotes for Query Workbench compatibility)
        bucket_name = self.bucket_list.split(",")[0]
        awr_config_query = f"""UPDATE system:awr SET location = '{bucket_name}', 
        interval = '60m', threshold = '30s'"""
        
        # Enable AWR
        awr_enable_query = "UPDATE system:awr SET enabled = true"
        
        try:
            # Execute the queries
            self.log.info(f"Running AUS query: {aus_query}")
            self.run_n1ql_query(aus_query, True)
            time.sleep(30)
            
            # Verify AUS settings
            verify_aus_query = "SELECT * FROM system:aus"
            aus_settings = self.run_n1ql_query(verify_aus_query, True)
            self.log.info(f"Current AUS settings: {aus_settings}")
            
            self.log.info(f"Running AWR config query: {awr_config_query}")
            self.run_n1ql_query(awr_config_query, True)
            time.sleep(30)
            
            self.log.info(f"Running AWR enable query: {awr_enable_query}")
            self.run_n1ql_query(awr_enable_query, True)
            time.sleep(30)
            
            # Verify AWR settings
            verify_awr_query = "SELECT * FROM system:awr"
            awr_settings = self.run_n1ql_query(verify_awr_query, True)
            self.log.info(f"Current AWR settings: {awr_settings}")
            
        except Exception as e:
            self.log.error(f"Error configuring AWR/AUS settings: {str(e)}")
            raise

    def disable_awr_aus(self):
        """Disable AWR and AUS settings for the cluster"""
        try:
            # Disable AUS
            aus_disable_query = "UPDATE system:aus SET enable = false"
            self.log.info(f"Running AUS disable query: {aus_disable_query}")
            self.run_n1ql_query(aus_disable_query, True)
            time.sleep(30)
            
            # Verify AUS settings
            verify_aus_query = "SELECT * FROM system:aus"
            aus_settings = self.run_n1ql_query(verify_aus_query, True)
            self.log.info(f"Current AUS settings after disable: {aus_settings}")
            
            # Disable AWR
            awr_disable_query = "UPDATE system:awr SET enabled = false"
            self.log.info(f"Running AWR disable query: {awr_disable_query}")
            self.run_n1ql_query(awr_disable_query, True)
            time.sleep(30)
            
            # Verify AWR settings
            verify_awr_query = "SELECT * FROM system:awr"
            awr_settings = self.run_n1ql_query(verify_awr_query, True)
            self.log.info(f"Current AWR settings after disable: {awr_settings}")
            
        except Exception as e:
            self.log.error(f"Error disabling AWR/AUS settings: {str(e)}")
            raise

    def set_plan_stability(self, mode="prepared_only"):
        """Configure plan stability mode for the cluster
        
        Args:
            mode: Plan stability mode - "prepared_only", "ad_hoc", "ad_hoc_read_only", or "off"
        """
        valid_modes = ["prepared_only", "ad_hoc", "ad_hoc_read_only", "off"]
        if mode not in valid_modes:
            raise ValueError(f"Invalid plan stability mode: {mode}. Must be one of {valid_modes}")
        
        query = f'UPDATE system:settings SET plan_stability.mode = "{mode}"'
        self.log.info(f"Running plan stability query: {query}")
        status, results, response = self._execute_query_rest(query)
        if not status:
            raise Exception(f"Failed to set plan stability: {response}")
        
        # Verify plan stability settings
        verify_query = "SELECT plan_stability FROM system:settings"
        self.log.info(f"Verifying plan stability settings")
        status, results, response = self._execute_query_rest(verify_query)
        self.log.info(f"Current plan stability settings: {results}")

    def verify_query_metadata(self, non_zero_check=False):
        """Verify QUERY_METADATA._system._query collection record count.
        
        Args:
            non_zero_check: If True, raises exception if count is zero.
                           If False, raises exception if count is non-zero.
        """
        query = "SELECT COUNT(*) as count FROM QUERY_METADATA._system._query"
        self.log.info(f"Checking QUERY_METADATA._system._query collection (non_zero_check={non_zero_check})")
        status, results, response = self._execute_query_rest(query)
        
        if not status:
            # Check if bucket/collection doesn't exist
            # Error format: "Keyspace not found in CB datastore: default:QUERY_METADATA ... No bucket named QUERY_METADATA"
            error_str = str(response).lower()
            if "keyspace not found" in error_str or "no bucket named" in error_str:
                self.log.info("QUERY_METADATA bucket does not exist, skipping check")
                return
            raise Exception(f"Failed to query QUERY_METADATA._system._query: {response}")
        
        count = 0
        if results and len(results) > 0:
            count = results[0].get('count', 0)
        
        self.log.info(f"QUERY_METADATA._system._query record count: {count}")
        
        if non_zero_check:
            if count == 0:
                raise Exception("QUERY_METADATA._system._query collection is empty but expected non-zero records.")
            self.log.info(f"QUERY_METADATA._system._query collection has {count} records as expected")
        else:
            if count != 0:
                raise Exception(f"QUERY_METADATA._system._query collection is not empty. Found {count} records.")
            self.log.info("QUERY_METADATA._system._query collection is empty as expected")

    def _execute_query_rest(self, statement):
        """
        Execute a N1QL query using REST API instead of SDK.
        This is needed for PREPARE/EXECUTE statements which SDK doesn't support directly.
        """
        port = 18093 if self.use_tls else 8093
        scheme = "https" if self.use_tls else "http"
        url = f"{scheme}://{self.connection_string}:{port}/query/service"
        
        auth = (self.username, self.password)
        payload = {"statement": statement}
        
        try:
            response = requests.post(url=url, data=payload, auth=auth, timeout=120, verify=False)
            result = response.json()
            
            if response.status_code == 200 and result.get("status") == "success":
                return True, result.get("results", []), result
            else:
                errors = result.get("errors", [])
                self.log.error(f"Query failed: {errors}")
                return False, [], result
                
        except requests.exceptions.RequestException as e:
            self.log.error(f"REST request failed: {str(e)}")
            return False, [], None

    def prepare_statements(self, bucket_name, statement_types, distance_algo="EUCLIDEAN_SQUARED", num_dimensions=128):
        """
        Create prepared statements for different query types:
        - scalar: Regular GSI scalar queries
        - vector_dense: Dense vector search queries (composite index)
        - vector_sparse: Sparse vector search queries
        - bhive_dense: Dense BHIVE vector queries
        - bhive_sparse: Sparse BHIVE vector queries
        """
        self.log.info(f"Creating prepared statements for types: {statement_types}")
        bucket_name = bucket_name.split(",")[0].strip()
        keyspace = f"`{bucket_name}`.`_default`.`_default`"
        
        self.prepared_statements = {}

        prepared_templates = {
            "scalar": {
                "name": "p_scalar_hotel",
                "statement": f"SELECT META().id, city FROM {keyspace} WHERE city LIKE $city_prefix LIMIT $limit_val"
            },
            "vector_dense": {
                "name": "p_vector_dense",
                "statement": f"SELECT META().id, APPROX_VECTOR_DISTANCE(vectors, $qvec, '{distance_algo}', $nprobe) AS score FROM {keyspace} ORDER BY APPROX_VECTOR_DISTANCE(vectors, $qvec, '{distance_algo}', $nprobe) LIMIT 10"
            },
            "vector_sparse": {
                "name": "p_vector_sparse",
                "statement": f"SELECT META().id, SPARSE_VECTOR_DISTANCE(embedding, $qvec_sparse, $nprobe) AS score FROM {keyspace} ORDER BY SPARSE_VECTOR_DISTANCE(embedding, $qvec_sparse, $nprobe) LIMIT 10"
            },
            "bhive_dense": {
                "name": "p_bhive_dense",
                "statement": f"SELECT META().id, APPROX_VECTOR_DISTANCE(vectors, $qvec, '{distance_algo}', $nprobe) AS score FROM {keyspace}  ORDER BY APPROX_VECTOR_DISTANCE(vectors, $qvec, '{distance_algo}', $nprobe) LIMIT 10"
            },
            "bhive_sparse": {
                "name": "p_bhive_sparse",
                "statement": f"SELECT META().id, SPARSE_VECTOR_DISTANCE(embedding, $qvec_sparse, $nprobe) AS score FROM {keyspace} ORDER BY SPARSE_VECTOR_DISTANCE(embedding, $qvec_sparse, $nprobe) LIMIT 10"
            }
        }

        for stmt_type in statement_types:
            stmt_type = stmt_type.strip()
            if stmt_type not in prepared_templates:
                self.log.warning(f"Unknown statement type: {stmt_type}, skipping")
                continue

            template = prepared_templates[stmt_type]
            prepare_stmt = f"PREPARE {template['name']} AS {template['statement']}"

            self.log.info(f"Preparing statement: {prepare_stmt}")
            try:
                status, results, response = self._execute_query_rest(prepare_stmt)
                if status:
                    self.prepared_statements[stmt_type] = template['name']
                    self.log.info(f"Successfully prepared {stmt_type}: {template['name']}")
                else:
                    self.log.error(f"Failed to prepare {stmt_type}")
            except Exception as e:
                self.log.error(f"Error preparing {stmt_type}: {str(e)}")

        self.log.info(f"Prepared statements created: {list(self.prepared_statements.keys())}")

    def execute_prepared(self, statement_types, iterations=100, duration=0, interval=1, 
                         validate=False, num_dimensions=128):
        """
        Execute prepared statements either for a fixed number of iterations
        or for a specified duration. Uses REST API for EXECUTE statements.
        """
        self.log.info(f"Executing prepared statements. Duration: {duration}s, "
                      f"Iterations: {iterations}, Interval: {interval}s")

        # If no prepared statements in memory, try to use the default names
        if not hasattr(self, 'prepared_statements') or not self.prepared_statements:
            self.prepared_statements = {}
            for stmt_type in statement_types:
                stmt_type = stmt_type.strip()
                default_names = {
                    "scalar": "p_scalar_hotel",
                    "vector_dense": "p_vector_dense", 
                    "vector_sparse": "p_vector_sparse",
                    "bhive_dense": "p_bhive_dense",
                    "bhive_sparse": "p_bhive_sparse"
                }
                if stmt_type in default_names:
                    self.prepared_statements[stmt_type] = default_names[stmt_type]

        # Read actual query vectors if available
        query_vectors = None
        try:
            query_vectors = self.read_query_file()
        except:
            pass

        execution_count = 0
        error_count = 0
        start_time = time.time()

        def should_continue():
            if duration > 0:
                return (time.time() - start_time) < duration
            return execution_count < iterations

        while should_continue():
            for stmt_type in statement_types:
                stmt_type = stmt_type.strip()
                if stmt_type not in self.prepared_statements:
                    self.log.debug(f"Skipping {stmt_type} - not prepared or not in requested types")
                    continue

                prepared_name = self.prepared_statements[stmt_type]
                
                # Build parameters based on statement type
                if stmt_type == "scalar":
                    params = {"city_prefix": "San%", "limit_val": 10}
                elif stmt_type in ["vector_dense", "bhive_dense"]:
                    if isinstance(query_vectors, list) and len(query_vectors) > 0:
                        idx = random.randint(0, len(query_vectors) - 1)
                        qvec = query_vectors[idx]
                    else:
                        qvec = [0.1] * num_dimensions
                    params = {"qvec": qvec, "nprobe": random.randint(50, 100)}
                elif stmt_type in ["vector_sparse", "bhive_sparse"]:
                    if query_vectors and isinstance(query_vectors, dict):
                        idx = random.choice(list(query_vectors.keys()))
                        sparse_data = query_vectors[idx]
                        params = {"qvec_sparse": sparse_data,
                                  "nprobe": random.randint(50, 100)}
                    else:
                        params = {"qvec_sparse": [[1, 5, 10], [0.5, 0.3, 0.2]],
                                  "nprobe": 50}
                else:
                    params = {}

                execute_stmt = f"EXECUTE {prepared_name}"
                if params:
                    params_json = json.dumps(params)
                    execute_stmt = f"EXECUTE {prepared_name} USING {params_json}"

                self.log.debug(f"Executing: {execute_stmt[:200]}...")
                try:
                    status, results, response = self._execute_query_rest(execute_stmt)
                    if status:
                        execution_count += 1
                        self.log.debug(f"Executed {prepared_name}, got {len(results)} results")
                        self.log.debug(f"Results for {prepared_name}: {results}")
                        if validate:
                            self.log.info(f"Executed {prepared_name}, got {len(results)} results")
                    else:
                        error_count += 1
                        self.log.warning(f"Execute {prepared_name} returned no status")
                except Exception as e:
                    error_count += 1
                    self.log.error(f"Error executing {prepared_name}: {str(e)}")

            if interval > 0:
                time.sleep(interval)

        elapsed = time.time() - start_time
        self.log.info(f"Prepared statement execution completed. "
                      f"Total executions: {execution_count}, Errors: {error_count}, "
                      f"Elapsed time: {elapsed:.2f}s")

    def drop_prepared_statements(self):
        """
        Drop all prepared statements created by this session. Uses REST API.
        """
        self.log.info("Dropping all prepared statements")

        prepared_names = [
            "p_scalar_hotel",
            "p_vector_dense",
            "p_vector_sparse",
            "p_bhive_dense",
            "p_bhive_sparse"
        ]

        for name in prepared_names:
            drop_stmt = f'DELETE FROM system:prepareds WHERE name = "{name}"'
            self.log.info(f"Dropping prepared statement: {name}")
            try:
                status, results, response = self._execute_query_rest(drop_stmt)
                self.log.info(f"Dropped {name}: {status}")
            except Exception as e:
                self.log.debug(f"Error dropping {name} (may not exist): {str(e)}")

        if hasattr(self, 'prepared_statements'):
            self.prepared_statements = {}
        self.log.info("Prepared statements dropped")

    def create_udf(self, bucket_name, num_udf_per_scope=10):
        """
        Create N number of UDFs on all scopes of a given bucket.
        Creates both SQL++ inline UDFs and JavaScript-backed UDFs.
        """
        self.log.info(f"Creating UDFs on bucket {bucket_name}, {num_udf_per_scope} per scope")
        
        # Get all scopes for the bucket
        get_scopes_query = f"SELECT raw name FROM system:scopes WHERE `bucket` = '{bucket_name}'"
        status, results, response = self._execute_query_rest(get_scopes_query)
        
        self.log.info(f"Scopes query status: {status}, results: {results}")
        
        if not status:
            self.log.error(f"Failed to get scopes for bucket {bucket_name}: {response}")
            # Fall back to _default scope
            results = ["_default"]
        
        if not results:
            results = ["_default"]
        
        # Include _default scope, exclude system scopes like _system
        scope_names = [f"`{bucket_name}`.`{scope}`" for scope in results if scope != '_system']
        self.log.info(f"Found scopes: {scope_names}")
        
        # Create JS library functions first
        self.log.info("Creating JavaScript library functions")
        port = 18093 if self.use_tls else 8093
        scheme = "https" if self.use_tls else "http"
        
        js_functions = [
            ("add", "function add(a, b) { return a + b; }"),
            ("sub", "function sub(a, b) { return a - b; }"),
            ("mul", "function mul(a, b) { return a * b; }"),
            ("div", "function div(a, b) { return a / b; }")
        ]
        
        for func_name, func_code in js_functions:
            url = f"{scheme}://{self.connection_string}:{port}/functions/v1/libraries/math/functions/{func_name}"
            try:
                response = requests.post(
                    url=url,
                    json={"name": func_name, "code": func_code},
                    auth=(self.username, self.password),
                    timeout=120,
                    verify=False
                )
                self.log.debug(f"Created JS function {func_name}: {response.status_code}")
            except Exception as e:
                self.log.debug(f"JS function {func_name} may already exist: {str(e)}")
        
        # UDF templates - mix of SQL++ inline and JavaScript-backed
        udf_templates = [
            "CREATE FUNCTION default:{keyspace}.fun1_{suffix}(arg1, arg2){{arg1 + arg2}}",
            "CREATE FUNCTION default:{keyspace}.fun2_{suffix}(a, b) LANGUAGE javascript AS \"add\" AT \"math\"",
            "CREATE FUNCTION default:{keyspace}.fun3_{suffix}(arg1, arg2){{arg1 - arg2}}",
            "CREATE FUNCTION default:{keyspace}.fun4_{suffix}(a, b) LANGUAGE javascript AS \"sub\" AT \"math\"",
            "CREATE FUNCTION default:{keyspace}.fun5_{suffix}(arg1, arg2){{arg1 * arg2}}",
            "CREATE FUNCTION default:{keyspace}.fun6_{suffix}(a, b) LANGUAGE javascript AS \"mul\" AT \"math\"",
            "CREATE FUNCTION default:{keyspace}.fun7_{suffix}(arg1, arg2){{arg1 / arg2}}",
            "CREATE FUNCTION default:{keyspace}.fun8_{suffix}(a, b) LANGUAGE javascript AS \"div\" AT \"math\""
        ]
        
        import string as string_module
        
        for scope in scope_names:
            for i in range(num_udf_per_scope):
                template = random.choice(udf_templates)
                suffix = ''.join(random.choices(string_module.ascii_uppercase + string_module.digits, k=6))
                udf_stmt = template.format(keyspace=scope, suffix=suffix)
                
                status, results, _ = self._execute_query_rest(udf_stmt)
                self.log.info(f"{udf_stmt} : {status}")
                time.sleep(0.25)
        
        self.log.info("UDF creation completed")

    def create_n1ql_udf(self, lib_name, lib_code=None, lib_filename=None):
        """
        Create a N1QL UDF library and function.
        If lib_code is not provided, creates a default library.
        """
        self.log.info(f"Creating N1QL UDF library: {lib_name}")
        
        port = 18093 if self.use_tls else 8093
        scheme = "https" if self.use_tls else "http"
        
        # Load library code from file if requested
        if lib_code is None and lib_filename:
            candidate_paths = [
                lib_filename,
                os.path.join(os.path.dirname(os.path.realpath(__file__)), lib_filename),
                os.path.join("/", lib_filename),
            ]
            for candidate in candidate_paths:
                if os.path.exists(candidate):
                    with open(candidate, "r") as fh:
                        lib_code = fh.read()
                    self.log.info(f"Loaded N1QL UDF library from {candidate}")
                    break

        # Default library code if not provided
        if lib_code is None:
            lib_code = '''
function run_n1ql_query(bucketname) {
    var query = "SELECT COUNT(*) as cnt FROM `" + bucketname + "`._default._default";
    var result = N1QL(query);
    return result;
}
'''
        
        # Create the library
        url = f"{scheme}://{self.connection_string}:{port}/evaluator/v1/libraries/{lib_name}"
        try:
            response = requests.post(
                url=url,
                data=lib_code,
                headers={'Content-Type': 'application/json'},
                auth=(self.username, self.password),
                timeout=120,
                verify=False
            )
            if response.status_code == 200:
                self.log.info(f"Created JS library {lib_name}")
            else:
                self.log.error(f"Failed to create library: {response.status_code} - {response.text}")
                return
        except Exception as e:
            self.log.error(f"Error creating library: {str(e)}")
            return
        
        # Create the N1QL function
        create_func_stmt = f"CREATE OR REPLACE FUNCTION run_n1ql_query(bucketname) LANGUAGE JAVASCRIPT AS 'run_n1ql_query' AT '{lib_name}'"
        status, results, _ = self._execute_query_rest(create_func_stmt)
        self.log.info(f"Create function result: {status}")

    def drop_udf(self, bucket_name):
        """
        Drop all UDFs for a given bucket.
        """
        self.log.info(f"Dropping all UDFs for bucket {bucket_name}")
        
        # Get all functions for the bucket
        get_functions_query = f"""
            SELECT raw 'DROP FUNCTION default:`' || identity.`bucket` || '`.`' || identity.`scope` || '`.`' || identity.name || '`'
            FROM system:functions
            WHERE identity.`bucket` = '{bucket_name}'
        """
        
        status, results, _ = self._execute_query_rest(get_functions_query)
        
        if status and results:
            for drop_stmt in results:
                drop_status, _, _ = self._execute_query_rest(drop_stmt)
                self.log.info(f"{drop_stmt} : {drop_status}")
                time.sleep(0.25)
        
        self.log.info("Drop UDFs completed")

    def get_udf_names(self, bucket_name, scope_name="_default"):
        """
        Get all UDF function names for a given bucket and scope.
        Returns a list of function names.
        """
        get_functions_query = f"""
            SELECT raw name
            FROM system:functions
            WHERE identity.`bucket` = '{bucket_name}' AND identity.`scope` = '{scope_name}'
        """
        
        status, results, _ = self._execute_query_rest(get_functions_query)
        
        if status and results:
            # Filter to get function names that match our pattern (fun1_xxx, fun2_xxx, etc.)
            udf_names = [r for r in results if r and r.startswith('fun')]
            self.log.info(f"Found UDFs: {udf_names}")
            return udf_names
        
        return []

    def run_udf_queries(self, bucket_name, scope_name="_default", num_queries=20):
        """
        Run queries that exercise UDFs.
        1. Gets UDF names from system:functions
        2. Loads UDF query templates
        3. Replaces placeholders and executes queries
        """
        self.log.info(f"Running UDF queries for {bucket_name}.{scope_name}")
        
        # Get UDF names
        udf_names = self.get_udf_names(bucket_name, scope_name)
        
        if not udf_names:
            self.log.warning(f"No UDFs found for {bucket_name}.{scope_name}, cannot run UDF queries")
            return
        
        # Load UDF query templates
        queries_file = os.path.join(os.path.dirname(__file__), 'queries.json')
        with open(queries_file, 'r') as f:
            all_queries = json.load(f)
        
        udf_templates = all_queries.get('hotel_udf', [])
        if not udf_templates:
            self.log.error("No hotel_udf templates found in queries.json")
            return
        
        # Build keyspace
        keyspace = f"`{bucket_name}`.`{scope_name}`.`_default`"
        
        # Execute queries with random UDF selection
        execution_count = 0
        error_count = 0
        
        for i in range(num_queries):
            template = random.choice(udf_templates)
            udf_name = random.choice(udf_names)
            
            # Build full UDF reference
            full_udf_ref = f"default:`{bucket_name}`.`{scope_name}`.{udf_name}"
            
            # Replace placeholders
            query = template.replace('keyspacenameplaceholder', keyspace)
            query = query.replace('UDF_PLACEHOLDER', full_udf_ref)
            
            # Execute
            self.log.debug(f"Executing UDF query: {query[:200]}...")
            status, results, _ = self._execute_query_rest(query)
            
            if status:
                execution_count += 1
                self.log.debug(f"UDF query succeeded, got {len(results)} results")
            else:
                error_count += 1
                self.log.warning(f"UDF query failed")
            
            time.sleep(0.5)
        
        self.log.info(f"UDF query execution completed. Success: {execution_count}, Errors: {error_count}")

    def run_n1ql_query(self, query, iterate_over_results=False, query_node=None, groundtruth_vectors=None,
                       validate_vector_query_results=False, groundtruth_file=None):
        query_info = self.query_catalog.get(query, {})
        query_vectors = self.read_query_file()
        index = 0
        limit_val = None
        vector_query = False
        if "qvec" in query:
            index = random.randint(0, len(query_vectors) - 1)
            self.log.debug(f"Query vectors {query_vectors[index]}")
            query = query.replace("qvec", str(query_vectors[index]))
            vector_query = True
        if "nprobe" in query:
            if self.nprobe:
                nprobe_val = self.nprobe
            elif "shoes" in self.template:
                # Extract number before 'M' from filename like 'idx_5M.ivecs'
                filter_value = int(groundtruth_file.split('M')[0].split('_')[-1])
                nprobe_val = self.calculate_nprobe(filter_value)
            else:
                nprobe_val = random.randint(50, 100)
            self.log.debug(f"Nprobe value is {nprobe_val}")
            if "SPARSE_VECTOR_DISTANCE" in query:
                # sparse: SPARSE_VECTOR_DISTANCE(vec, qvec, nprobe[, topNScan[, topNTerms]]) - the 4th argument is an integer
                # topNScan (Hyperscale/BHIVE only), not the boolean rerank flag of APPROX_VECTOR_DISTANCE, so never append ", true"
                with_topn = self.sparse_topn and self.bhive_queries
                query = query.replace("nprobe", f"{nprobe_val}, {self.sparse_topn}" if with_topn else str(nprobe_val))
            #uncomment once reranking can be enabled
            elif self.bhive_queries and self.dense_topn:
                # APPROX_VECTOR_DISTANCE(vec, qvec, metric, nprobes, rerank, topNScan): topNScan (BHIVE only) needs nprobes
                # and rerank to be present, so rerank is passed explicitly (true for random queries)
                rerank = "true" if random.random() < 0.2 else "false"
                query = query.replace("nprobe", f"{nprobe_val}, {rerank}, {self.dense_topn}")
            elif self.bhive_queries and random.random() < 0.2:
                #reranking set to true for random queries
                concat_str = str(nprobe_val) + ", true"
                query = query.replace("nprobe", concat_str)
            else:
                query = query.replace("nprobe", str(nprobe_val))
        if "DIST_ALGO" in query:
            query = query.replace("DIST_ALGO", self.distance_algo)
        if "LIMIT_N_VAL" in query:
            if self.sparse_recall:
                limit_val = self.sparse_limit  # exact groundtruth is top-10; qrels recall uses the whole LIMIT
            elif self.validate_vector_query_results:
                limit_val = 100
            else:
                limit_val = random.randint(1, 100)
            query = query.replace("LIMIT_N_VAL", str(limit_val))
        if self.base64_encoding:
            query = query.replace("vectors", "decode_vector(vectors,false)")
        if self.xattrs:
            query = query.replace("vectors", "meta().xattrs.vectors")
        self._count_query_execution(query_info)
        client_context_id = str(uuid.uuid4())
        if self.use_sdk:
            if not self.cluster:
                self.create_cluster_object()
            consistency_type = random.getrandbits(1)
            profile_enabled = self.enable_scan_report and (random.random() < 0.2)
            qo_kwargs = {"timeout": self.timeout, "client_context_id": client_context_id}
            # Template queries are always profiled so index usage can be checked: profile=phases is
            # enough to see which scans ran, timings also carries the scan report
            profile_mode = "timings" if profile_enabled else ("phases" if query_info else None)
            if profile_mode:
                qo_kwargs["profile"] = profile_mode
            if profile_enabled:
                self.log.debug("Profile timings requested for query: %s", self._abbreviate_vectors(query))
                include_scanreport_detailed = bool(random.getrandbits(1))
                if include_scanreport_detailed:
                    # The SDK has no scanreport_wait option, so pass it through as a raw request
                    # parameter. The query service accepts a duration of at most 15s.
                    scanreport_wait = f"{random.randint(1, 15)}s"
                    self.log.debug(f"Including scanreport_wait={scanreport_wait} for query "
                                   f"{self._abbreviate_vectors(query)}")
                    qo_kwargs["raw"] = {"scanreport_wait": scanreport_wait}
            if consistency_type:
                qo_kwargs["scan_consistency"] = QueryScanConsistency.REQUEST_PLUS
            self.log.debug(f"Query options for this query: {qo_kwargs}")
            query_opts = QueryOptions(**qo_kwargs)
            result = []
            run_error = None
            meta = None
            start_time = time.time()
            try:
                self.log.debug(f"running query - {self._abbreviate_vectors(query)} via SDK with parameters {qo_kwargs}")
                result_obj = self.cluster.query(query, query_opts)
                # The SDK runs the query lazily: errors surface here, while iterating the rows,
                # so this must stay inside the try that records the failure.
                materialized_rows = []
                if iterate_over_results:
                    materialized_rows = [r for r in result_obj.rows()]
                elif self.enable_scan_report or profile_mode:
                    # The metadata is only complete once every row has been read, but nothing uses the
                    # rows here, so drain them without keeping them in memory
                    for _ in result_obj.rows():
                        pass
                elapsed = time.time() - start_time
                meta = None
                if iterate_over_results or self.enable_scan_report or profile_mode:
                    try:
                        meta = result_obj.metadata()
                    except Exception as e:
                        self.log.debug(f"Could not read query metadata: {type(e).__name__}: {e}")
                usage_problem = None
                if profile_mode:
                    usage_problem = self.index_usage_problem(self._metadata_value(meta, "profile"))
                    if usage_problem:
                        self.record_query_failure("no_index_scan", query, usage_problem, query_info,
                                                  client_context_id=client_context_id,
                                                  request_id=self._metadata_value(meta, "request_id"),
                                                  elapsed=elapsed)
                # Only queries run with profile=timings carry the #indexStats scan report, and only
                # index scans produce one
                if profile_enabled and not usage_problem:
                    problem = self.index_stats_problem(meta)
                    if problem:
                        self.record_query_failure("index_stats_validation", query, problem, query_info,
                                                  client_context_id=client_context_id,
                                                  request_id=self._metadata_value(meta, "request_id"),
                                                  elapsed=elapsed)
                if iterate_over_results:
                    result = materialized_rows
                    if vector_query and limit_val and len(result) != limit_val:
                        self.record_query_failure("result_count_mismatch", query,
                                                  f"Incorrect result count. Limit: {limit_val}, Got: {len(result)}",
                                                  query_info, client_context_id=client_context_id,
                                                  request_id=self._metadata_value(meta, "request_id"),
                                                  elapsed=elapsed)
            except CouchbaseException as ex:
                details = self._couchbase_error_details(ex)
                run_error = f"{type(ex).__name__}: {details['message']}"
                self.record_query_failure("error", query, details["message"], query_info,
                                          error_code=details["code"], error_type=type(ex).__name__,
                                          query_node=details["node"],
                                          client_context_id=details["client_context_id"] or client_context_id,
                                          elapsed=time.time() - start_time)
            except Exception as ex:
                run_error = f"{type(ex).__name__}: {ex}"
                self.record_query_failure("error", query, str(ex), query_info, error_type=type(ex).__name__,
                                          client_context_id=client_context_id, elapsed=time.time() - start_time)
                self.log.debug("Unexpected error during query execution", exc_info=True)
            if validate_vector_query_results:
                elapsed_first = round(time.time() - start_time, 3)
                # A vector query that returns no rows and no error (seen returning in tens of ms, against seconds for a normal
                # BHIVE scan): keep what the service said about it and ask once more, so the log shows whether the same
                # statement is empty again (deterministic) or not (a transient state)
                warnings, retry_count = [], None
                if vector_query and not result and not run_error:
                    try:
                        warnings = [str(w)[:240] for w in (self._metadata_value(meta, "warnings") or [])][:5]
                    except Exception:
                        pass
                    try:
                        retry_count = sum(1 for _ in self.cluster.query(query, query_opts).rows())
                    except Exception as e:
                        retry_count = f"error: {str(e)[:100]}"
                self.compute_recall(groundtruth_vectors, result, index, {
                    "query_id": query_info.get("query_id"), "keyspace": query_info.get("keyspace"), "limit": limit_val,
                    "elapsed_s": elapsed_first, "error": run_error,
                    "scan_consistency": "request_plus" if consistency_type else "not_bounded",
                    "client_context_id": client_context_id,
                    "request_id": self._metadata_value(meta, "request_id"),
                    "warnings": warnings, "retry_result_count": retry_count})
            return result
        else:
            self.log.debug(f"running query - {self._abbreviate_vectors(query)} via rest")
            if not query_node:
                query_node = random.choice(self.get_all_n1ql_nodes())
            auth = (self.username, self.password)
            payload = {"statement": query, "client_context_id": client_context_id}
            if query_info:
                payload["profile"] = "phases"
            api = f"http://" + query_node + ':8093/query/service'
            start_time = time.time()
            try:
                response = requests.post(url=api, auth=auth, timeout=self.timeout, verify=False,
                                         headers={'Content-Type': 'application/json'}, json=payload)
                elapsed = time.time() - start_time
                if response.status_code == 200:
                    body = response.json()
                    if query_info:
                        usage_problem = self.index_usage_problem(body.get("profile"))
                        if usage_problem:
                            self.record_query_failure("no_index_scan", query, usage_problem, query_info,
                                                      query_node=query_node, client_context_id=client_context_id,
                                                      request_id=body.get("requestID"), elapsed=elapsed)
                    return body['results']
                error_code, message = None, response.text
                try:
                    body = response.json()
                    first_error = (body.get("errors") or [{}])[0]
                    error_code, message = first_error.get("code"), first_error.get("msg", message)
                    request_id = body.get("requestID")
                except ValueError:
                    request_id = None
                self.record_query_failure("error", query, message, query_info, error_code=error_code,
                                          error_type=f"HTTP {response.status_code}", query_node=query_node,
                                          client_context_id=client_context_id, request_id=request_id,
                                          elapsed=elapsed)
            except Exception as ex:
                self.record_query_failure("error", query, str(ex), query_info, error_type=type(ex).__name__,
                                          query_node=query_node, client_context_id=client_context_id,
                                          elapsed=time.time() - start_time)

    @staticmethod
    def _abbreviate_vectors(statement):
        """Collapse vector literals so statements stay readable in logs."""
        return VECTOR_LITERAL_RE.sub(lambda m: f"[<{m.group(0).count(',') + 1} values>]", str(statement))

    @staticmethod
    def _metadata_value(meta, name):
        """Read a field from a QueryMetaData object (accessor methods) or a raw dict."""
        if meta is None:
            return None
        if isinstance(meta, dict):
            return meta.get(name)
        try:
            value = getattr(meta, name, None)
            return value() if callable(value) else value
        except Exception:
            return None

    @staticmethod
    def _couchbase_error_details(ex):
        """Pull code, message, node and client_context_id out of a CouchbaseException's error context."""
        ctx = getattr(ex, "context", None)
        code = getattr(ctx, "first_error_code", None) or None
        message = getattr(ctx, "first_error_message", None) or None
        if not message:
            # Timeouts and other client-side errors carry no server error; use the exception text
            message = getattr(ex, "message", None) or str(ex)
        return {"code": code,
                "message": message,
                "node": getattr(ctx, "last_dispatched_to", None),
                "client_context_id": getattr(ctx, "client_context_id", None)}

    def _count_query_execution(self, query_info):
        key = (query_info.get("query_id", "adhoc"), query_info.get("keyspace", "n/a"))
        with self._failures_lock:
            self.query_exec_counts[key] = self.query_exec_counts.get(key, 0) + 1

    def record_query_failure(self, kind, statement, message, query_info=None, error_code=None, error_type=None,
                             query_node=None, client_context_id=None, request_id=None, elapsed=None):
        """Record one failed query execution.

        kind is "error" (query raised), "result_count_mismatch" (vector query returned fewer rows than
        its LIMIT), "no_index_scan" (plan used a sequential scan or no index) or "index_stats_validation"
        (scan report in the profile was missing/invalid).
        Failures are aggregated per kind/query/keyspace/error so memory stays bounded on long runs.
        """
        query_info = query_info or {}
        query_id = query_info.get("query_id", "adhoc")
        keyspace = query_info.get("keyspace", "n/a")
        message = str(message).strip()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Errors are split by code/type; for the validation kinds the message varies per run
        # (e.g. "Limit: 37, Got: 12"), so it is kept as a sample instead.
        key = (kind, query_id, keyspace, error_code, error_type)
        if kind == "error" and error_code is None:
            key += (message[:120],)
        sample_id = client_context_id or request_id
        with self._failures_lock:
            group = self.query_failure_groups.get(key)
            if group is None:
                group = {"kind": kind, "query_id": query_id, "keyspace": keyspace, "error_code": error_code,
                         "error_type": error_type, "count": 0, "first_seen": now, "last_seen": now,
                         "messages": {}, "nodes": {}, "ids": [], "min_elapsed": None, "max_elapsed": None,
                         "statement": self._abbreviate_vectors(statement)}
                self.query_failure_groups[key] = group
            group["count"] += 1
            group["last_seen"] = now
            if message in group["messages"] or len(group["messages"]) < MAX_SAMPLES_PER_FAILURE_GROUP:
                group["messages"][message] = group["messages"].get(message, 0) + 1
            if query_node:
                group["nodes"][query_node] = group["nodes"].get(query_node, 0) + 1
            if sample_id and len(group["ids"]) < MAX_SAMPLES_PER_FAILURE_GROUP:
                group["ids"].append(sample_id)
            if elapsed is not None:
                group["min_elapsed"] = elapsed if group["min_elapsed"] is None else min(group["min_elapsed"], elapsed)
                group["max_elapsed"] = elapsed if group["max_elapsed"] is None else max(group["max_elapsed"], elapsed)
        self.log.debug(f"QUERY_FAILURE kind={kind} query={query_id} keyspace={keyspace} code={error_code} "
                       f"type={error_type} node={query_node} client_context_id={client_context_id} "
                       f"request_id={request_id} elapsed={elapsed} message={message} "
                       f"statement={self._abbreviate_vectors(statement)}")

    def get_query_failure_count(self):
        with self._failures_lock:
            return sum(group["count"] for group in self.query_failure_groups.values())

    def print_failure_summary(self):
        """Log failed queries grouped by query/keyspace/error. Every line of a group starts with
        QUERY_FAILURE[<n>] so `grep QUERY_FAILURE` on the console log shows the full picture."""
        with self._failures_lock:
            groups = sorted(self.query_failure_groups.values(), key=lambda g: g["count"], reverse=True)
            exec_counts = dict(self.query_exec_counts)
        total_execs = sum(exec_counts.values())
        total_failures = sum(group["count"] for group in groups)
        if not groups:
            self.log.info(f"===== QUERY FAILURE SUMMARY: no failed queries ({total_execs} executions) =====")
            return
        self.log.info(f"===== QUERY FAILURE SUMMARY: {total_failures} failed executions in {len(groups)} groups "
                      f"({total_execs} executions in total) =====")
        for n, group in enumerate(groups, 1):
            tag = f"QUERY_FAILURE[{n}]"
            execs = exec_counts.get((group["query_id"], group["keyspace"]))
            ratio = f"{group['count']}/{execs}" if execs else str(group["count"])
            lines = [f"{tag} {group['kind']}: query {group['query_id']} on {group['keyspace']} - "
                     f"{ratio} executions failed"]
            error = " ".join(str(part) for part in (group["error_code"], group["error_type"]) if part)
            for message, count in group["messages"].items():
                lines.append(f"{tag}   error      : {error + ': ' if error else ''}{message}"
                             f"{f' (x{count})' if len(group['messages']) > 1 else ''}")
            lines.append(f"{tag}   seen       : first {group['first_seen']}, last {group['last_seen']}")
            if group["nodes"]:
                nodes = ", ".join(f"{node} x{count}" for node, count in
                                  sorted(group["nodes"].items(), key=lambda item: item[1], reverse=True))
                lines.append(f"{tag}   query nodes: {nodes}")
            if group["min_elapsed"] is not None:
                lines.append(f"{tag}   elapsed    : min {group['min_elapsed']:.2f}s, max {group['max_elapsed']:.2f}s")
            if group["ids"]:
                lines.append(f"{tag}   context ids: {', '.join(group['ids'])}")
            lines.append(f"{tag}   statement  : {group['statement']}")
            for line in lines:
                self.log.info(line)
        self.log.info("===== END QUERY FAILURE SUMMARY =====")

    @staticmethod
    def index_usage_problem(profile):
        """Return why a query did not scan a GSI index, or None if it did.

        Uses the profile's phaseOperators, which profile=phases and profile=timings both return:
        index scans show up as indexScan.GSI / indexScan.CVI, a query that fell back to a
        sequential scan (no usable index) as primaryScan.Seq.
        """
        if not profile:
            return "no profile in query metadata"
        operators = profile.get("phaseOperators") or {}
        if operators.get("primaryScan.Seq"):
            return f"sequential scan used instead of an index (phaseOperators: {json.dumps(operators, sort_keys=True)})"
        if not any(op.startswith(("indexScan", "indexCountScan", "primaryScan")) for op in operators):
            return f"no index scan in the plan (phaseOperators: {json.dumps(operators, sort_keys=True)})"
        return None

    @classmethod
    def _find_gsi_scans(cls, node, found=None):
        """Return every GSI scan operator in a profile operator tree, including ones nested under
        DistinctScan/UnionScan/IntersectScan and in subqueries."""
        if found is None:
            found = []
        if isinstance(node, dict):
            operator = str(node.get("#operator", ""))
            if operator.startswith(("IndexScan", "PrimaryScan")) and node.get("using") == "gsi":
                found.append(node)
            node = list(node.values())
        if isinstance(node, list):
            for child in node:
                if isinstance(child, (dict, list)):
                    cls._find_gsi_scans(child, found)
        return found

    def validate_index_stats(self, metadata) -> bool:
        return self.index_stats_problem(metadata) is None

    def index_stats_problem(self, metadata):
        """Return why the #indexStats scan report in a profiled query's metadata is invalid, or None if valid."""
        if metadata is None:
            return "no query metadata"
        # metadata may be a raw dict OR a Couchbase QueryMetaData object. The object is
        # not subscriptable, so read the profile via its accessor rather than metadata["profile"].
        try:
            profile = self._metadata_value(metadata, "profile")
        except Exception as e:
            return f"could not read profile from metadata: {type(e).__name__}: {e}"
        if not profile:
            return "no profile in metadata (was the query run with profile=timings?)"
        try:
            execution_timings = profile["executionTimings"]
        except (KeyError, TypeError) as ke:
            self.log.debug(f"Profile structure: {profile}")
            return f"missing expected key in profile structure: {ke}"
        # Scan operators are not always direct children: array index scans nest them as
        # DistinctScan -> "scan" -> IndexScan3, UnionScan holds several, and subqueries have
        # their own. Every GSI scan should carry its own report.
        scans = self._find_gsi_scans(execution_timings)
        if not scans:
            return "no GSI index scan operator in execution plan"
        for scan in scans:
            problem = self._index_stats_problem(scan.get("#indexStats"))
            if problem:
                return f"{scan.get('#operator')} on {scan.get('index')}: {problem}"
        self.log.debug("validate_index_stats: Validation passed")
        return None

    @staticmethod
    def _index_stats_problem(index_stats):
        """Return why one scan operator's #indexStats is invalid, or None if valid."""
        if not index_stats:
            return "no #indexStats"
        if not isinstance(index_stats.get("defn"), list):
            return f"defn is not a list, got {type(index_stats.get('defn')).__name__}"
        num_scans = index_stats.get("num_scans")
        if not isinstance(num_scans, int) or num_scans <= 0:
            return f"num_scans is invalid, got {num_scans!r}"
        avg_ns = index_stats.get("srvr_avg_ns", {})
        for key in ["scan", "total", "wait"]:
            if key not in avg_ns or avg_ns[key] < 0:
                return f"srvr_avg_ns[{key}] is missing or negative: {avg_ns.get(key)}"
        total_counts = index_stats.get("srvr_total_counts", {})
        for key in ["bytesRead", "rowsReturn", "rowsScan"]:
            if key not in total_counts or total_counts[key] < 0:
                return f"srvr_total_counts[{key}] is missing or negative: {total_counts.get(key)}"
        return None

    def get_services_map(self):
        """
        Populate the service map for all nodes in the cluster.
        """
        cluster_url = "http://" + self.connection_string + ":8091/pools/default"
        self.log.info(f"Rest URL is {cluster_url}")
        node_map = []
        try:
            response = requests.get(cluster_url, auth=(
                self.username, self.password), verify=False)
            if response.ok:
                response = json.loads(response.text)
                for node in response["nodes"]:
                    cluster_node = dict()
                    cluster_node["hostname"] = node["hostname"].replace(":8091", "")
                    cluster_node["services"] = node["services"]
                    mem_used = int(node["memoryTotal"]) - int(node["memoryFree"])
                    cluster_node["memUsage"] = round(
                        float(mem_used / float(node["memoryTotal"]) * 100), 2)
                    cluster_node["cpuUsage"] = round(
                        node["systemStats"]["cpu_utilization_rate"], 2)
                    cluster_node["status"] = node["status"]
                    cluster_node["clusterMembership"] = node["clusterMembership"]
                    node_map.append(cluster_node)
            else:
                response.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            self.log.error("HTTPError getting response from {1} : {0}".format(str(errh), cluster_url))
        except requests.exceptions.ConnectionError as errc:
            self.log.error("ConnectionError getting response from {1} : {0}".format(str(errc), cluster_url))
        except requests.exceptions.Timeout as errt:
            self.log.error("Timeout getting response from {1} : {0}".format(str(errt), cluster_url))
        except requests.exceptions.RequestException as err:
            self.log.error("Error getting response from {1} : {0}".format(str(err), cluster_url))
        self.log.info(f"Node map is {node_map}")
        return node_map

    def generate_queries(self, template=None):
        self.log.debug("Generating queries.")
        generated_queries = []
        with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'queries.json')) as f:
            data = f.read()
        query_json = json.loads(data)
        templates_list = [template] if template else self.template.split(",")
        # (query_id, statement) where query_id is "<template>#<position in queries.json>"
        queries_list = []
        for template_name in templates_list:
            queries_list += [(f"{template_name}#{n}", item) for n, item in enumerate(query_json[template_name])]
        self.log.debug(f"Queries per template {len(queries_list)}")
        keyspaces = self.fetch_keyspaces_list()
        if not keyspaces:
            # Without this the workload silently runs zero queries for its whole duration
            default_note = ("_default._default is skipped (--skip_default true); pass --skip_default false "
                            "to query it" if self.skip_default else "_default._default is included")
            raise Exception(f"No keyspaces to query in bucket(s) {self.bucket_list or '(all)'}: only "
                            f"scope_*.coll_* collections are queried and {default_note}")
        for keyspace in keyspaces:
            bucket, scope, collection = keyspace.split(".")
            for query_id, item in queries_list:
                query_statement = item.replace("keyspacenameplaceholder", f"`{bucket}`.`{scope}`.`{collection}`")
                if self.sparse_recall and " where " in item.lower():
                    continue  # groundtruth is unfiltered, so only unfiltered statements give a valid recall
                generated_queries.append(query_statement)
                query_info = {"query_id": query_id, "keyspace": keyspace}
                self.query_catalog[query_statement] = query_info
                # shoes templates carry "<statement>; <groundtruth file>" and are split before running
                self.query_catalog.setdefault(query_statement.split(";")[0], query_info)
        return generated_queries

    def find_nodes_with_service(self, service):
        """
        From the service map, find all nodes running the specified service and return the node list.
        """
        nodelist = []
        node_map = self.get_services_map()
        for node in node_map:
            if service == "all":
                nodelist.append(node["hostname"])
            else:
                if service in node["services"]:
                    nodelist.append(node["hostname"])
        return nodelist

    def get_all_n1ql_nodes(self):
        query_nodes = self.find_nodes_with_service("n1ql")
        return query_nodes

    def fetch_active_requests(self):
        query = "select value x from active_requests() as x;"
        results = self.run_analytics_query(query)
        query_results = [row for row in results.rows()]
        active_query_context_id_list = []
        for query in query_results:
            if query['state'] == 'running':
                active_query_context_id_list.append(query['clientContextID'])
        return active_query_context_id_list

    def columnar_admin_rest_call(self, endpoint):
        rest_url = self.fetch_rest_url()
        url = "https://" + rest_url + ":18095/" + endpoint
        self.log.info(f"Will send request to {url} ")
        response = requests.get(url, auth=(
            self.username, self.password), verify=False, timeout=300)
        if response.ok:
            return response.json()

    def fetch_columnar_active_requests(self):
        response = self.columnar_admin_rest_call("analytics/admin/active_requests")
        self.log.info(f"Response is {response} ")
        return response

    def fetch_columnar_completed_requests(self):
        response = self.columnar_admin_rest_call("analytics/admin/completed_requests")
        return response

    def cancel_random_queries(self, cancel_query_count=5):
        active_requests = self.fetch_columnar_active_requests()
        for _ in range(cancel_query_count):
            context_id_to_cancel = random.choice(active_requests)
            query = f"cancel {context_id_to_cancel}"
            self.run_analytics_query(query=query)

    def poll_for_failed_queries(self):
        time_now = time.time()
        failed_query_metadata, failed_query_count = {}, 0
        while time.time() - time_now < self.duration:
            response_json = self.run_analytics_query(query="completed_requests()")
            if response_json:
                for query in response_json[0]:
                    self.log.debug(f"Parsing {query}")
                    if query['jobStatus'].lower() not in ['terminated', 'pending', 'running', 'null']:
                        failed_query_count += 1
                        if query['requestTime'] not in failed_query_metadata:
                            failed_query_metadata[query['requestTime']] = query
                if failed_query_count > 0:
                    self.log.error(f"Number of failed queries so far {failed_query_count} "
                                   f"and their metadata {failed_query_metadata}")
                self.log.debug(f"Sleeping for 300 seconds before next iteration")
                time.sleep(300)
        if failed_query_count > 0:
            raise Exception("There are failed queries in the completed_requests call. Check logs")

    def run_query_workload(self, num_concurrent_queries=5, refresh_duration=1800):
        self.log.info("Running query workload")
        time_now = time.time()
        time_last_refresh = time.time()
        queries = self.generate_queries()
        query_node, query_nodes = None, None
        if not self.capella:
            self.log.info("Not capella run so fetching query nodes")
            query_nodes = self.get_all_n1ql_nodes()
        groundtruth_vectors = None
        groundtruth_file = None  # Initialize groundtruth_file as None
        if self.query_type == 'analytics':
            method = self.run_analytics_query
        elif self.query_type == 'n1ql':
            if self.validate_vector_query_results:
                groundtruth_vectors = self.read_ground_truth_file()
                self.log.debug(f"Length of the groundtruth vectors array {len(groundtruth_vectors)}")
            method = self.run_n1ql_query
        else:
            raise Exception("Allowed service values - analytics/n1ql")
        while time.time() - time_now < self.duration:
            if time.time() - time_last_refresh >= refresh_duration:
                queries = self.generate_queries()
                time_last_refresh = time.time()
            query_tasks = []
            with ThreadPoolExecutor() as executor_main:
                if len(queries) < num_concurrent_queries:
                    queries_chosen = queries
                else:
                    queries_chosen = random.sample(queries, num_concurrent_queries)
                for query in queries_chosen:
                    if not self.capella:
                        query_node = random.choice(query_nodes)
                    if self.query_type == 'analytics':
                        query_task = executor_main.submit(method, query, True)
                    else:
                        if "shoes" in self.template and self.validate_vector_query_results:
                            self.log.debug("Entering shoe template block to read groundtruth")
                            query, groundtruth_file = query.split(";")
                            groundtruth_file = groundtruth_file.lstrip(" ")
                            groundtruth_file_path = f"/gnd/{groundtruth_file}"
                            self.log.debug(f"Groundtruth file {groundtruth_file_path}")
                            groundtruth_vectors = self.read_ground_truth_file(groundtruth_file_path)
                            self.log.debug(f"Length of the groundtruth vectors array {len(groundtruth_vectors)}")
                            self.log.debug(f"Query is - {query}")
                        query_task = executor_main.submit(method, query, True, query_node, groundtruth_vectors,
                                                          self.validate_vector_query_results, groundtruth_file)
                    query_tasks.append(query_task)
            for task in query_tasks:
                try:
                    task.result()
                except CouchbaseException as ex:
                    details = self._couchbase_error_details(ex)
                    statement = getattr(ex.context, "statement", None) or ""
                    self.record_query_failure("error", statement, details["message"],
                                              self.query_catalog.get(statement), error_code=details["code"],
                                              error_type=type(ex).__name__, query_node=details["node"],
                                              client_context_id=details["client_context_id"])
                except Exception:
                    # Log the FULL exception (type, message, file:line, traceback) instead of
                    # just the class, and rate-limit it: a persistent per-query error would
                    # otherwise print hundreds of thousands of identical lines and flood the run.
                    self._unexpected_error_count = getattr(self, "_unexpected_error_count", 0) + 1
                    if self._unexpected_error_count <= 5:
                        self.log.exception("Unexpected error while awaiting query task result")
                    elif self._unexpected_error_count % 1000 == 0:
                        self.log.warning(
                            "Unexpected error while awaiting query task result "
                            "(suppressed after first 5; %d occurrences so far)",
                            self._unexpected_error_count)

            sleep_duration = random.randint(10, 60)
            time.sleep(sleep_duration)
        self.log.info(f"Exiting query workload loop Current time {time.time()}  start time {time_now} "
                      f" Duration {self.duration}")

    def periodic_print_recall_stats(self, frequency=30):
        time_now = time.time()
        while time.time() - time_now < self.duration:
            self.print_recall_stats()
            time.sleep(frequency * 60)  # Convert minutes to seconds

    def print_recall_stats(self):
        if self.qrels_queries:
            self.log.info(f"QRELS recall@{self.sparse_limit}: {100 * self.qrels_sum / self.qrels_queries:.2f}% "
                          f"over {self.qrels_queries} queries")
        table = BeautifulTable()
        table.column_headers = ["Recall range", "Query count", "Percentage"]
        self.log.debug(f"Recall dict {self.recall_dict}")
        total_query_count = sum(self.recall_dict.values())
        if self.smoke_test_run:
            # Calculate queries with recall < 70%
            low_recall_count = 0
            for range_idx in self.recall_dict.keys():
                if range_idx < 7:  # ranges 0-6 represent 0-69% recall
                    low_recall_count += self.recall_dict[range_idx]
            
            low_recall_percentage = (low_recall_count / total_query_count) * 100 if total_query_count > 0 else 0
            self.log.info(f"Percentage of queries with recall < 70%: {low_recall_percentage:.2f}%")
            
            if low_recall_percentage > 20:
                raise Exception(f"Smoke test failed: {low_recall_percentage:.2f}% of queries have recall < 70%, which exceeds the 20% threshold")
        else:
            for item in sorted(self.recall_dict.keys()):  # Sort keys for consistent order
                range_start = item * 10
                range_end = min((item + 1) * 10, 100)  # Cap the end range at 100
                range_recall = f"{range_start}" if range_start == range_end else f"{range_start} to {range_end}"
                table.append_row([range_recall, self.recall_dict[item], 100 * self.recall_dict[item] / total_query_count])
            print(table)

    def get_rebalance_status(self):
        endpoint = f"{self.connection_string}/pools/default/rebalanceProgress"
        self.log.info(f"Endpoint used for is_rebalance_running {endpoint}")
        response = requests.get(endpoint, auth=(
            self.username, self.password), verify=False, timeout=300)
        rebalance_progress = False
        if response.ok:
            response = json.loads(response.text)
            rebalance_progress = response['status']
            self.log.info(f"Rebalance_progress {rebalance_progress}")
        return rebalance_progress

    def run_scans_validation(self):
        queries_list = self.generate_queries(template="hotel_scans_validation")
        scan_results_map_before = dict()
        for query in queries_list[:int(self.sample_size)]:
            scan_results_pre_rebalance = self.run_n1ql_query(query, True, None, None, False)
            scan_results_map_before[query] = scan_results_pre_rebalance
        self.log.info("Pre-rebalance scans complete")
        time.sleep(60)
        rebal_status = None
        time_now = time.time()
        while not rebal_status and time.time() - time_now < 600:
            rebal_status = self.get_rebalance_status()
            if rebal_status == "running":
                break
            time.sleep(60)
        if rebal_status != "running":
            raise Exception("Rebalance did not get triggered despite waiting 10 mins")
        rebal_status = None
        while not rebal_status and time.time() - time_now < 72000:
            rebal_status = self.get_rebalance_status()
            if rebal_status == "none":
                break
            time.sleep(60)
        if rebal_status != "none":
            raise Exception("Rebalance did not get complete despite waiting 20 hours")
        for query in scan_results_map_before.keys():
            scan_results_after_rebalance = self.run_n1ql_query(query, True, None, None, False)
            diffs = DeepDiff(scan_results_after_rebalance, scan_results_map_before[query], ignore_order=True)
            if diffs:
                self.log.error(f"Mismatch in query result before and after rebalance. Select query {query}\n\n. "
                               f"Result before \n\n {scan_results_map_before[query]}."
                               f"Result after \n \n {scan_results_after_rebalance}")
                raise Exception(f"Mismatch in query {query} results before and after rebalance")
        self.log.info("Scan results validation successful")

    def create_primary_index(self):
        primary_index_name = f"#primary{random.randint(0, 1000)}"
        keyspaces = self.fetch_keyspaces_list()
        for keyspace in keyspaces:
            bucket, scope, collection = keyspace.split(".")
            query = f"`create primary index {primary_index_name} on {bucket}`.`{scope}`.`{collection}`"
            self.run_n1ql_query(query=query)
        return primary_index_name

    def drop_primary_index(self, primary_index_name):
        keyspaces = self.fetch_keyspaces_list()
        for keyspace in keyspaces:
            bucket, scope, collection = keyspace.split(".")
            query = f"drop primary index {primary_index_name} on {bucket}`.`{scope}`.`{collection}`"
            self.run_n1ql_query(query=query)

    def data_validation(self):
        primary_index = self.create_primary_index()
        errors = []
        queries_list = self.generate_queries(template="hotel_scans_validation")
        for query in queries_list:
            self.log.info(f"GSI query {query}")
            scan_results_gsi = self.run_n1ql_query(query, True, None, None, False)
            primary_query = query.replace("where", f"USE INDEX(`{primary_index}`) where")
            self.log.info(f"Primary query {primary_query}")
            scan_results_primary = self.run_n1ql_query(primary_query, True, None, None, False)
            diffs = DeepDiff(scan_results_gsi, scan_results_primary, ignore_order=True)
            if diffs:
                self.log.error(f"Mismatch in query result between primary and gsi scans. Select query {query}\n\n. "
                               f"Results via GSI \n\n {scan_results_gsi}."
                               f"Results via primary \n \n {scan_results_primary}")
                errors_obj = dict()
                errors_obj["scan_results_gsi"] = scan_results_gsi
                errors_obj["scan_results_primary"] = scan_results_primary
                errors_obj["query"] = query
                errors.append(errors_obj)
        self.drop_primary_index(primary_index)
        if errors:
            raise Exception(f"Mismatch in query results between primary and gsi {errors}")


if __name__ == '__main__':
    # Dump the native/Python stack of the crashing thread to stderr on a fatal signal
    # (e.g. SIGSEGV from the SDK). Without this a crash is just a silent exit 139 and,
    # because cp-cli removes the container afterwards, the cause is unrecoverable.
    faulthandler.enable()
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--connection_string", help="SDK connection string")
    parser.add_argument("-u", "--username", help="username", default="Administrator")
    parser.add_argument("-p", "--password", help="password", default="password")
    parser.add_argument("-t", "--timeout", help="query timeout", default=1800)
    parser.add_argument("-b", "--template", help="doc template", default="product")
    parser.add_argument("-d", "--duration", help="duration for which the action needs to run",
                        default=3600)
    parser.add_argument("-q", "--num_concurrent_queries", help="number of queries to be run concurrently",
                        default=5)
    parser.add_argument("-dr", "--refresh_duration", help="duration for which the action needs to run",
                        default=1800)
    parser.add_argument("-a", "--action", help="SDK connection string", default="run_query_workload")
    parser.add_argument("-sd", "--use_sdk", help="use sdk or rest. true for use sdk",
                        default="true")
    parser.add_argument("-f", "--query_type", help="analytics/n1ql", default="analytics")
    parser.add_argument("-v", "--validate_vector_query_results", help="analytics/n1ql", default="false")
    parser.add_argument("-z", "--run_vector_queries", help="do you want to run vector scans?", default="false")
    parser.add_argument("-qf", "--query_file", help="fvecs file to be used for queries", default="/sift_query.fvecs")
    parser.add_argument("-qv", "--num_query_vectors", help="Number of groundtruth vectors", default=10000, type=int)
    parser.add_argument("-gf", "--groundtruth_file", help="ground truth file to be used for vector queries",
                        default="/sift_groundtruth.ivecs")
    parser.add_argument("-gtv", "--num_groundtruth_vectors", help="Number of groundtruth vectors",
                        default=100, type=int)
    parser.add_argument("-sz", "--sample_size", help="Number of groundtruth vectors",
                        default=20, type=int)
    parser.add_argument("-da", "--distance_algo", help="ground truth file to be used for vector queries",
                        default="L2")
    parser.add_argument("-bl", "--bucket_list", help="ground truth file to be used for vector queries",
                        default=None)
    parser.add_argument("-ut", "--use_tls", help="ground truth file to be used for vector queries",
                        default="true")
    parser.add_argument("-ca", "--capella", help="ground truth file to be used for vector queries",
                        default="true")
    parser.add_argument("-en", "--base64", help="ground truth file to be used for vector queries",
                        default="false")
    parser.add_argument("-xa", "--xattrs", help="ground truth file to be used for vector queries",
                        default="false")
    parser.add_argument("-skd", "--skip_default", help="ground truth file to be used for vector queries",
                        default="true")
    parser.add_argument("-pf", "--print_frequency", help="ground truth file to be used for vector queries",
                        default=5, type=int)
    parser.add_argument("-bhi", "--run_bhive_queries", help="ground truth file to be used for vector queries",
                        default="false")
    parser.add_argument("-ll", "--log_level", help="logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)", 
                        default="INFO")
    parser.add_argument("-st", "--smoke_test_run", help="True or False. Is it a smoke test run?", 
                        default="false")
    parser.add_argument("-sr", "--enable_scan_report", help="True or False. Is it a scan report?", 
                        default="false")
    parser.add_argument("--recall_file", default=None,
                        help="run_query_workload with --validate_vector_query_results: write the recall (histogram, query "
                             "count, mean recall) of the run to this JSON file")
    parser.add_argument("--dense_topn", type=int, default=None,
                        help="topNScan (6th argument of APPROX_VECTOR_DISTANCE) for dense BHIVE queries (needs --run_bhive_queries true); "
                             "rerank is then passed explicitly (true for ~20%% of queries); default: not passed")
    parser.add_argument("--sparse_topn", type=int, default=None,
                        help="topNScan (4th argument of SPARSE_VECTOR_DISTANCE) for sparse BHIVE queries (needs --run_bhive_queries true); default: not passed")
    parser.add_argument("--keyspace_list", default=None,
                        help="comma-separated bucket.scope.collection to query, instead of discovering scope_*/coll_* (and _default "
                             "unless --skip_default true); use when the data sits in one known collection")
    parser.add_argument("--qrels_file", default=None,
                        help="sparse recall: JSON list (one entry per query-vector row) of relevant passage ids, e.g. /msmarco_qrels.json")
    parser.add_argument("--sparse_limit", type=int, default=10,
                        help="sparse recall: LIMIT used for validated queries (exact recall = exact top-10 found within this many results)")
    parser.add_argument("--sparse_id_offset", type=int, default=0,
                        help="sparse recall: subtract this from the numeric suffix of the doc key to get the groundtruth row id")
    parser.add_argument("--nprobe", type=int, default=None,
                        help="Fixed nprobe for every vector query (default: derived from the filtering ratio / random 50-100)")
    parser.add_argument("--statement_types", default="scalar,vector_dense,vector_sparse,bhive_dense,bhive_sparse",
                        help="Comma-separated list of prepared statement types")
    parser.add_argument("--prepared_iterations", type=int, default=100,
                        help="Number of iterations to execute prepared statements")
    parser.add_argument("--prepared_duration", type=int, default=0,
                        help="Duration in seconds to run prepared statement execution (0 for iteration-based)")
    parser.add_argument("--prepared_interval", type=int, default=1,
                        help="Interval in seconds between prepared statement executions")
    parser.add_argument("--validate_prepared", default="false",
                        help="Validate prepared statement results")
    parser.add_argument("--num_dimensions", type=int, default=128,
                        help="Number of dimensions for vector queries")
    parser.add_argument("--num_udf_per_scope", type=int, default=10,
                        help="Number of UDFs to create per scope")
    parser.add_argument("--lib_name", default="n1qludf",
                        help="Name for the N1QL JS UDF library")
    parser.add_argument("--lib_filename", default=None,
                        help="Filename for the N1QL JS UDF library")
    parser.add_argument("--num_udf_queries", type=int, default=20,
                        help="Number of UDF queries to execute")
    parser.add_argument("--plan_stability_mode", default="prepared_only",
                        help="Plan stability mode: prepared_only, ad_hoc, ad_hoc_read_only, or off")
    parser.add_argument("--non_zero_check", default="false",
                        help="For verify_query_metadata: if true, expect non-zero records; if false, expect zero")
    args = parser.parse_args()
    query_manager = QueryManager(args.connection_string, args.username, args.password, int(args.timeout),
                                 int(args.duration), args.template, args.use_sdk, args.query_type, args.query_file,
                                 args.groundtruth_file, args.validate_vector_query_results, args.distance_algo,
                                 args.bucket_list, args.use_tls, args.capella, args.skip_default,
                                 args.num_groundtruth_vectors, args.num_query_vectors, args.base64,
                                 args.xattrs, args.sample_size, args.run_bhive_queries, args.print_frequency,
                                 args.log_level, args.smoke_test_run, args.enable_scan_report, nprobe=args.nprobe)
    query_manager.sparse_id_offset = args.sparse_id_offset
    query_manager.sparse_limit = args.sparse_limit
    query_manager.keyspace_list = args.keyspace_list
    query_manager.sparse_topn = args.sparse_topn
    query_manager.dense_topn = args.dense_topn
    if args.qrels_file:
        with open(args.qrels_file) as qf:
            query_manager.qrels = json.load(qf)
    args.validate_vector_query_results = True if args.validate_vector_query_results == "true" else False
    try:
        if args.action == "run_query_workload":
            query_manager.run_query_workload(int(args.num_concurrent_queries), int(args.refresh_duration))
            if args.validate_vector_query_results and args.run_vector_queries:
                if args.recall_file:
                    # before print_recall_stats: a smoke gate may raise there
                    query_manager.write_recall_file(args.recall_file, params={
                        "connection_string": args.connection_string, "bucket_list": args.bucket_list,
                        "nprobe": args.nprobe, "distance_algo": args.distance_algo, "duration": args.duration,
                        "num_concurrent_queries": args.num_concurrent_queries,
                        "num_query_vectors": args.num_query_vectors,
                        "num_groundtruth_vectors": args.num_groundtruth_vectors,
                        "run_bhive_queries": args.run_bhive_queries, "query_type": args.query_type})
                query_manager.print_recall_stats()
                smoke_run = args.smoke_test_run == "true"
                # if not smoke_run:
                #     raise Exception("Raising dummy exception to print the recall stats in the console log")
        elif args.action == "run_scans_validation":
            query_manager.run_scans_validation()
        elif args.action == "data_validation":
            query_manager.data_validation()
        elif args.action == "poll_for_failed_queries":
            query_manager.poll_for_failed_queries()
        elif args.action == "cancel_random_queries":
            query_manager.cancel_random_queries(int(args.num_concurrent_queries))
        elif args.action == "fetch_active_requests":
            query_manager.fetch_columnar_active_requests()
        elif args.action == "set_awr_aus":
            query_manager.set_awr_aus()
        elif args.action == "disable_awr_aus":
            query_manager.disable_awr_aus()
        elif args.action == "set_plan_stability":
            query_manager.set_plan_stability(args.plan_stability_mode)
        elif args.action == "verify_query_metadata":
            query_manager.verify_query_metadata(non_zero_check=(args.non_zero_check == "true"))
        elif args.action == "prepare_statements":
            statement_types = args.statement_types.split(",")
            query_manager.prepare_statements(
                bucket_name=args.bucket_list,
                statement_types=statement_types,
                distance_algo=args.distance_algo,
                num_dimensions=args.num_dimensions
            )
        elif args.action == "execute_prepared":
            statement_types = args.statement_types.split(",")
            query_manager.execute_prepared(
                statement_types=statement_types,
                iterations=args.prepared_iterations,
                duration=args.prepared_duration,
                interval=args.prepared_interval,
                validate=(args.validate_prepared == "true"),
                num_dimensions=args.num_dimensions
            )
        elif args.action == "drop_prepared_statements":
            query_manager.drop_prepared_statements()
        elif args.action == "create_udf":
            query_manager.create_udf(
                bucket_name=args.bucket_list,
                num_udf_per_scope=args.num_udf_per_scope
            )
        elif args.action == "create_n1ql_udf":
            query_manager.create_n1ql_udf(lib_name=args.lib_name, lib_filename=args.lib_filename)
        elif args.action == "drop_udf":
            query_manager.drop_udf(bucket_name=args.bucket_list)
        elif args.action == "run_udf_queries":
            query_manager.run_udf_queries(
                bucket_name=args.bucket_list,
                num_queries=args.num_udf_queries
            )
        else:
            raise Exception("Actions allowed - run_query_workload | poll_for_failed_queries "
                            "| cancel_random_queries | run_scans_validation | data_validation "
                            "| fetch_active_requests | set_awr_aus | disable_awr_aus | set_plan_stability "
                            "| verify_query_metadata | prepare_statements | execute_prepared "
                            "| drop_prepared_statements | create_udf | create_n1ql_udf | drop_udf | run_udf_queries")
    except KeyboardInterrupt:
        if args.validate_vector_query_results and args.run_vector_queries:
            query_manager.print_recall_stats()
        raise
    finally:
        # Final, grep-able (QUERY_FAILURE) summary of failed queries; query failures do not change the exit code
        if args.action == "run_query_workload" or query_manager.get_query_failure_count():
            query_manager.print_failure_summary()

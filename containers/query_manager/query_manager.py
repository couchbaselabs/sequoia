import argparse
import logging
import time
import random
import json
import os
import sys
from dns import resolver
import struct
import requests
import numpy as np
from beautifultable import BeautifulTable
from os.path import splitext
from deepdiff import DeepDiff
from datetime import datetime, timedelta
import pytz
from concurrent.futures import ThreadPoolExecutor
from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster
from couchbase.options import (ClusterOptions, ClusterTimeoutOptions,
                               QueryOptions, AnalyticsOptions)
from couchbase.exceptions import CouchbaseException
from couchbase.cluster import QueryScanConsistency
from couchbase.exceptions import CouchbaseException, QueryErrorContext
import threading

class QueryManager:
    def __init__(self, connection_string, username, password, timeout, duration, doc_template, use_sdk, query_type,
                 query_file, groundtruth_file, validate_vector_query_results, distance_algo, bucket_list, use_tls,
                 capella="false", skip_default="false", num_groundtruth_vectors=100, num_query_vectors=10000,
                 base64_encoding="false", xattrs="false", sample_size=20, bhive_queries=False, print_frequency=30,
                 log_level="INFO", smoke_test_run="false"):
        self.connection_string = connection_string
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
        self.smoke_test_run = smoke_test_run == "true"
        self.query_error_obj = dict()
        self.print_frequency = print_frequency
        self.log = logging.getLogger("query_manager")
        # Set log level based on parameter
        log_level = getattr(logging, log_level.upper(), logging.INFO)
        self.log.setLevel(log_level)
        ch = logging.StreamHandler()
        self.recall_dict = dict()
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
        return

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
        if "ivecs" in file_path:
            vectors = self.read_ivecs(file_path, end)
        elif "bvecs" in file_path:
            vectors = self.read_bvecs(file_path, end)
        return vectors

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
            return self.read_file(groundtruth_file_path, 10000)
        return self.read_file(self.groundtruth_file, self.num_groundtruth_vectors)

    def read_query_file(self):
        if "small" in self.query_file:
            return self.read_fvecs_file(self.query_file, 0, 100)
        elif "gist" in self.query_file:
            return self.read_fvecs_file(self.query_file, 0, 1000)
        elif "sift_query" in self.query_file:
            return self.read_fvecs_file(self.query_file, 0, 10000)
        return self.read_file(self.query_file, self.num_query_vectors)

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

    def compute_recall(self, groundtruth_vectors, result, index):
        groundtruth_result_vector = groundtruth_vectors[index]
        query_res_list = [item['id'] for item in result]
        if 'shoes' not in self.template:
            query_res_list = [int(s.lstrip('doc')) - 1 for s in query_res_list]
            self.log.info(f"Query result {query_res_list}")
        self.log.debug(f"Groundtruth {groundtruth_result_vector[:100]}")
        self.log.debug(f"Query result {query_res_list}")
        recall_percentage = len(list(set(groundtruth_result_vector[:100]).intersection(query_res_list)))
        self.update_recall_dict(recall_percentage)

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

    def run_n1ql_query(self, query, iterate_over_results=False, query_node=None, groundtruth_vectors=None,
                       validate_vector_query_results=False, groundtruth_file=None):
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
            if "shoes" in self.template:
                # Extract number before 'M' from filename like 'idx_5M.ivecs'
                filter_value = int(groundtruth_file.split('M')[0].split('_')[-1])
                nprobe_val = self.calculate_nprobe(filter_value)
            else:
                nprobe_val = random.randint(50, 100)
            self.log.debug(f"Nprobe value is {nprobe_val}")
            #uncomment once reranking can be enabled
            run_with_reranking = random.random() < 0.2
            if self.bhive_queries and run_with_reranking:
                #reranking set to true for random queries
                concat_str = str(nprobe_val) + ", true"
                query = query.replace("nprobe", concat_str)
            else:
                query = query.replace("nprobe", str(nprobe_val))
        if "DIST_ALGO" in query:
            query = query.replace("DIST_ALGO", self.distance_algo)
        if "LIMIT_N_VAL" in query:
            if self.validate_vector_query_results:
                limit_val = 100
            else:
                limit_val = random.randint(1, 100)
            query = query.replace("LIMIT_N_VAL", str(limit_val))
        if self.base64_encoding:
            query = query.replace("vectors", "decode_vector(vectors,false)")
        if self.xattrs:
            query = query.replace("vectors", "meta().xattrs.vectors")
        if self.use_sdk:
            if not self.cluster:
                self.create_cluster_object()
            consistency_type = random.getrandbits(1)
            if consistency_type:
                query_opts = QueryOptions(timeout=self.timeout, scan_consistency=QueryScanConsistency.REQUEST_PLUS)
            else:
                query_opts = QueryOptions(timeout=self.timeout)
            result_obj = None
            try:
                self.log.debug(f"running query - {query} via SDK")
                result_obj = self.cluster.query(query, query_opts)
            except CouchbaseException as ex:
                if isinstance(ex.context, QueryErrorContext):
                    request_time = None
                    if result_obj:
                        execution_time = result_obj.metadata().metrics().execution_time()
                        if execution_time:
                            request_time = execution_time
                    if hasattr(ex.context, 'execution_time'):
                        request_time = ex.context.execution_time or result_obj.request_time
                    item_dict = {ex.context.client_context_id: {
                        "statement": ex.context.statement,
                        "first_error_message": ex.context.first_error_message,
                        "request_time": request_time
                    }}
                    self.query_error_obj.update(item_dict)
            except:
                print("Unexpected error:", sys.exc_info()[0])
            result = []
            if iterate_over_results:
                result = [row for row in result_obj.rows()]
                if vector_query:
                    if limit_val and len(result) != limit_val:
                        self.log.debug(f"Query {query} has fetched incorrect number of results "
                                       f"though a limit was specified. Limit specified {limit_val}. "
                                       f"Result length {len(result)}")
                        item_dict = {result_obj.metadata().request_id(): {"statement": query,
                                                                      "first_error_message": f"Query {query} has fetched incorrect number of results "
                                                                                             f"though a limit was specified. Limit specified {limit_val}. "
                                                                                             f"Result length {len(result)}"}}
                        self.query_error_obj.update(item_dict)
            if validate_vector_query_results:
                self.compute_recall(groundtruth_vectors, result, index)
            return result
        else:
            self.log.debug(f"running query - {query} via rest")
            if query_node:
                query_node = random.choice(self.get_all_n1ql_nodes())
            auth = (self.username, self.password)
            payload = {"statement": query}
            api = f"http://" + query_node + ':8093/query/service'
            try:
                response = requests.post(url=api, auth=auth, timeout=self.timeout, verify=False,
                                         headers={'Content-Type': 'application/json'}, json=payload)
                if response.status_code == 200:
                    return response.json()['results']
            except:
                pass

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
        queries_list = []
        if template:
            queries_list = query_json[template]
        else:
            if "," in self.template:
                templates_list = self.template.split(",")
                for template in templates_list:
                    queries_list += query_json[template]
            else:
                queries_list = query_json[self.template]
        self.log.debug(f"Queries per template {len(queries_list)}")
        keyspaces = self.fetch_keyspaces_list()
        for keyspace in keyspaces:
            bucket, scope, collection = keyspace.split(".")
            for item in queries_list:
                query_statement = item.replace("keyspacenameplaceholder", f"`{bucket}`.`{scope}`.`{collection}`")
                generated_queries.append(query_statement)
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

    def print_query_errors(self):
        """Prints current query errors in a formatted table"""
        query_error_resp_dict = self.get_query_errors_dict()
        if query_error_resp_dict:
            self.log.info("========================Queries that have ended in errors==============================================================")
            table = BeautifulTable()
            table.column_headers = ["Request ID", "Statement", "Error", "Request Time"]
            # Set reasonable widths for all columns
            table.column_widths = [40, 60, 60, 40]
            # Configure word wrapping
            table.maxwidth = 200
            table.wrap_on_max_width = True
            
            for item in query_error_resp_dict.keys():
                request_time = query_error_resp_dict[item].get("requestTime", "NA")
                statement = query_error_resp_dict[item]["statement"]
                # Truncate statement if longer than 50 characters
                # if len(statement) > 50:
                #     statement = statement[:47] + "..."
                table.append_row([item,
                                statement,
                                query_error_resp_dict[item]["first_error_message"],
                                request_time])
            self.log.info("\n" + str(table))
            self.query_error_obj = {}

    def run_query_workload(self, num_concurrent_queries=5, refresh_duration=1800):
        self.log.info("Running query workload")
        # Start periodic error printing in a separate thread
        error_thread = threading.Thread(target=self.periodic_print_errors, 
                                      args=(self.print_frequency,))  # Print every 30 minutes
        error_thread.daemon = True
        error_thread.start()
        # Start periodic recall stats printing if needed
        # if self.validate_vector_query_results:
        #     stats_thread = threading.Thread(target=self.periodic_print_recall_stats, 
        #                                   args=(self.print_frequency,))
        #     stats_thread.daemon = True
        #     stats_thread.start()
        query_tasks = []
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
                    if isinstance(ex.context, QueryErrorContext):
                        item_dict = {ex.context.client_context_id: {"statement": ex.context.statement,
                                                                    "first_error_message": ex.context.first_error_message}}
                        self.query_error_obj.update(item_dict)
                except:
                    print("Unexpected error:", sys.exc_info()[0])

            sleep_duration = random.randint(10, 60)
            time.sleep(sleep_duration)
        self.log.info(f"Exiting query workload loop Current time {time.time()}  start time {time_now} "
                      f" Duration {self.duration}")

    def get_query_errors_dict(self):
        return self.query_error_obj

    def periodic_print_recall_stats(self, frequency=30):
        time_now = time.time()
        while time.time() - time_now < self.duration:
            self.print_recall_stats()
            time.sleep(frequency * 60)  # Convert minutes to seconds

    def print_recall_stats(self):
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

    def periodic_print_errors(self, frequency=30):
        """Prints error stats every n minutes"""
        time_now = time.time()
        while time.time() - time_now < self.duration:
            self.print_query_errors()
            time.sleep(frequency * 60)  # Convert minutes to seconds


if __name__ == '__main__':
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
    args = parser.parse_args()
    query_manager = QueryManager(args.connection_string, args.username, args.password, int(args.timeout),
                                 int(args.duration), args.template, args.use_sdk, args.query_type, args.query_file,
                                 args.groundtruth_file, args.validate_vector_query_results, args.distance_algo,
                                 args.bucket_list, args.use_tls, args.capella, args.skip_default,
                                 args.num_groundtruth_vectors, args.num_query_vectors, args.base64,
                                 args.xattrs, args.sample_size, args.run_bhive_queries, args.print_frequency,
                                 args.log_level)
    args.validate_vector_query_results = True if args.validate_vector_query_results == "true" else False
    try:
        if args.action == "run_query_workload":
            query_manager.run_query_workload(int(args.num_concurrent_queries), int(args.refresh_duration))
            if args.validate_vector_query_results and args.run_vector_queries:
                query_manager.print_recall_stats()
                smoke_run = args.smoke_test_run == "true"
                if not smoke_run:
                    raise Exception("Raising dummy exception to print the recall stats in the console log")
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
        else:
            raise Exception("Actions allowed - run_query_workload | poll_for_failed_queries "
                            "| cancel_random_queries | run_scans_validation | data_validation "
                            "| fetch_active_requests | set_awr_aus | disable_awr_aus")
    except KeyboardInterrupt:
        if args.validate_vector_query_results and args.run_vector_queries:
            query_manager.print_recall_stats()
        raise
    finally:
        query_error_resp_dict = query_manager.get_query_errors_dict()
        if query_error_resp_dict:
            print(
                "========================Queries that have ended in errors==============================================================")
            try:
                table = BeautifulTable()
                table.column_headers = ["Request ID", "Statement", "Error", "Request Time"]
                # Set reasonable widths for all columns
                table.column_widths = [40, 60, 60, 20]
                # Configure word wrapping
                table.maxwidth = 180
                table.wrap_on_max_width = True
                
                for item in query_error_resp_dict.keys():
                    try:
                        request_time = str(query_error_resp_dict[item].get("requestTime", "NA"))
                        statement = str(query_error_resp_dict[item].get("statement", ""))
                        error_message = str(query_error_resp_dict[item].get("first_error_message", ""))
                        
                        # Truncate statement if longer than 50 characters
                        if len(statement) > 50:
                            statement = statement[:47] + "..."
                        if len(error_message) > 50:
                            error_message = error_message[:47] + "..."
                            
                        table.append_row([str(item),
                                        statement,
                                        error_message,
                                        request_time])
                    except Exception as e:
                        print(f"Error processing row for item {item}: {str(e)}")
                        continue
                
                # Only print if table has rows
                if len(table.rows) > 0:
                    print(table)
                else:
                    print("No valid error data to display")
                    
            except Exception as e:
                print(f"Error creating error table: {str(e)}")
                print("Raw error data:", query_error_resp_dict)

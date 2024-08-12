import argparse
import logging
import time
import random
import json
import os
from dns import resolver
import struct
import requests
import numpy as np

from os.path import splitext
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster
from couchbase.options import (ClusterOptions, ClusterTimeoutOptions,
                               QueryOptions, AnalyticsOptions)
from couchbase.exceptions import CouchbaseException
from couchbase.cluster import QueryScanConsistency
from couchbase.exceptions import CouchbaseException, QueryErrorContext

class QueryManager:
    def __init__(self, connection_string, username, password, timeout, duration, doc_template, use_sdk, query_type,
                 query_file, groundtruth_file, validate_vector_query_results, distance_algo, bucket_list, use_tls,
                 capella="false", skip_default="false", num_groundtruth_vectors=100, num_query_vectors=10000):
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
        self.query_error_obj = dict()
        self.log = logging.getLogger("query_manager")
        self.log.setLevel(logging.INFO)
        ch = logging.StreamHandler()
        self.recall_dict = dict()
        ch.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        ch.setFormatter(formatter)
        self.log.addHandler(ch)
        timestamp = str(datetime.now().strftime('%Y%m%dT_%H%M%S'))
        fh = logging.FileHandler("./query_manager-{0}.log".format(timestamp))
        fh.setFormatter(formatter)
        self.log.addHandler(fh)

    def get_recall_dict(self):
        return self.recall_dict

    def update_recall_dict(self, recall_percentage):
        rounded_pct = round(recall_percentage / 10)
        if rounded_pct in self.recall_dict:
            self.recall_dict[rounded_pct] += 1
        else:
            self.recall_dict[rounded_pct] = 1
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
                self.log.info(f"Bucket list param passed. Using {bucket_list}")
            else:
                bucket_list = self.get_all_buckets()
            for bucket_name in bucket_list:
                self.log.info(f"Bucket name {bucket_name}")
                bucket_obj = self.cluster.bucket(bucket_name)
                scopes = bucket_obj.collections().get_all_scopes()
                self.log.info("Bucket name {}".format(bucket_name))
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
        elif "fvecs" in file_path:
            vectors = self.read_fvecs(file_path)
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
        self.log.info(f"Query result {result}")
        self.log.info(f"Ground truth result {groundtruth_vectors[index]}")
        query_res_list = [item['id'] for item in result]
        recall_percentage = len(list(set(groundtruth_result_vector).intersection(query_res_list)))
        self.log.info(f"Recall percentage {recall_percentage}")
        self.update_recall_dict(recall_percentage)

    def run_n1ql_query(self, query, iterate_over_results=False, query_node=None, groundtruth_vectors=None,
                       validate_vector_query_results=False):
        query_vectors = self.read_query_file()
        index = 0
        vector_query = False
        if "qvec" in query:
            index = random.randint(0, len(query_vectors)-1)
            self.log.debug(f"Query vectors {query_vectors[index]}")
            query = query.replace("qvec", str(query_vectors[index]))
        if "nprobe" in query:
            nprobe_val = random.randint(15, 30)
            query = query.replace("nprobe", str(nprobe_val))
        if "DIST_ALGO" in query:
            query = query.replace("DIST_ALGO", self.distance_algo)
        if "LIMIT_N_VAL" in query:
            self.log.info(f"limit val is {self.limit_val}")
            query = query.replace("LIMIT_N_VAL", str(self.limit_val))
            vector_query = True
        self.log.info(f"Query is {query}")
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
                result_obj = self.cluster.query(query, query_opts)
            except:
                return result_obj
            result = []
            if iterate_over_results:
                result = [row for row in result_obj.rows()]
                if vector_query:
                    if len(result) != self.limit_val:
                        self.log.error(f"Query {query} has fetched incorrect number of results "
                                       f"though a limit was specified. Response {dir(result_obj)}")
                        raise Exception(f"Query {query} has fetched incorrect number of results "
                                        f"though a limit was specified. Response {dir(result_obj)}")
            if validate_vector_query_results:
                self.log.info(f"Index is {index}")
                self.compute_recall(groundtruth_vectors, result, index)
            return result
        else:
            self.log.info(f"running query - {query} via rest")
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

    def generate_queries(self):
        self.log.info("Generating queries.")
        generated_queries = []
        with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'queries.json')) as f:
            data = f.read()
        query_json = json.loads(data)
        if self.template not in query_json:
            raise Exception("Add your query blueprint json file")
        queries_list = query_json[self.template]
        keyspaces = self.fetch_keyspaces_list()
        for keyspace in keyspaces:
            bucket, scope, collection = keyspace.split(".")
            for item in queries_list:
                query_statement = item.replace("keyspacenameplaceholder", f"`{bucket}`.`{scope}`.`{collection}`")
                generated_queries.append(query_statement)
        self.log.info(f"=====================Generated a total of {len(generated_queries)} queries=====================")
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
            context_id_to_cancel = random.choice(active_query_context_id_list)
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
        query_tasks = []
        time_now = time.time()
        time_last_refresh = time.time()
        queries = self.generate_queries()
        query_node, query_nodes = None, None
        if not self.capella:
            self.log.info("Not capella run so fetching query nodes")
            query_nodes = self.get_all_n1ql_nodes()
        groundtruth_vectors = None
        if self.query_type == 'analytics':
            method = self.run_analytics_query
        elif self.query_type == 'n1ql':
            if self.validate_vector_query_results:
                groundtruth_vectors = self.read_ground_truth_file()
                self.log.info(f"Length of the groundtruth vectors array {len(groundtruth_vectors)}")
            method = self.run_n1ql_query
        else:
            raise Exception("Allowed service values - analytics/n1ql")
        while time.time() - time_now < self.duration:
            if time.time() - time_last_refresh >= refresh_duration:
                queries = self.generate_queries()
                time_last_refresh = time.time()
                self.log.info("Entering refresh block")
            with ThreadPoolExecutor() as executor_main:
                queries_chosen = random.sample(queries, num_concurrent_queries)
                for query in queries_chosen:
                    if not self.capella:
                        query_node = random.choice(query_nodes)
                    if self.query_type == 'analytics':
                        query_task = executor_main.submit(method, query, True)
                    else:
                        if "shoes" in self.template and self.validate_vector_query_results:
                            self.log.info("Entering shoe template block to read groundtruth")
                            query, groundtruth_file = query.split(";")
                            groundtruth_file = groundtruth_file.lstrip(" ")
                            groundtruth_file_path = f"/gnd/{groundtruth_file}"
                            self.log.info(f"Groundtruth file {groundtruth_file_path}")
                            groundtruth_vectors = self.read_ground_truth_file(groundtruth_file_path)
                        query_task = executor_main.submit(method, query, True, query_node, groundtruth_vectors,
                                                          self.validate_vector_query_results)
                        if self.validate_vector_query_results:
                            self.print_recall_stats()
                    query_tasks.append(query_task)
            for task in query_tasks:
                try:
                    task.result()
                except CouchbaseException as ex:
                    self.log.error(f"Query task ended in exception. Ignoring this")
                    if isinstance(ex.context, QueryErrorContext):
                        item_dict = {ex.context.client_context_id: {"statement": ex.context.statement,
                                                                    "first_error_message": ex.context.first_error_message}}
                        self.query_error_obj.update(item_dict)
            sleep_duration = random.randint(10, 60)
            self.log.info(f"Query batch completed. Will sleep for {sleep_duration} seconds")
            time.sleep(sleep_duration)
        self.log.info(f"Exiting query workload loop Current time {time.time()}  start time {time_now} "
                      f" Duration {self.duration}")
        if self.validate_vector_query_results:
            self.print_recall_stats()

    def get_query_errors_dict(self):
        return self.query_error_obj

    def periodic_print_recall_stats(self, frequency=10):
        while time.time() - time_now < self.duration:
            self.print_recall_stats()
            time.sleep(frequency*60)

    def print_recall_stats(self):
        self.log.info(f"Recall dict is {self.recall_dict}")
        for key, value in self.recall_dict.items():
            lower_bound = key * 10 - 5
            upper_bound = min(100, key * 10 + 5)
            self.log.info(f"The number of queries with recall between {lower_bound} percent and {upper_bound} percent = {value}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--connection_string", help="SDK connection string")
    parser.add_argument("-u", "--username", help="username", default="Administrator")
    parser.add_argument("-p", "--password", help="password", default="password")
    parser.add_argument("-t", "--timeout", help="query timeout", default=300)
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
    parser.add_argument("-qf", "--query_file", help="fvecs file to be used for queries", default="/sift_query.fvecs")
    parser.add_argument("-qv", "--num_query_vectors", help="Number of groundtruth vectors", default=10000, type=int)
    parser.add_argument("-gf", "--groundtruth_file", help="ground truth file to be used for vector queries",
                        default="/sift_groundtruth.ivecs")
    parser.add_argument("-gtv", "--num_groundtruth_vectors", help="Number of groundtruth vectors",
                        default=100, type=int)
    parser.add_argument("-da", "--distance_algo", help="ground truth file to be used for vector queries",
                        default="L2")
    parser.add_argument("-bl", "--bucket_list", help="ground truth file to be used for vector queries",
                        default=None)
    parser.add_argument("-ut", "--use_tls", help="ground truth file to be used for vector queries",
                        default="true")
    parser.add_argument("-ca", "--capella", help="ground truth file to be used for vector queries",
                        default="true")
    parser.add_argument("-skd", "--skip_default", help="ground truth file to be used for vector queries",
                        default="true")
    parser.add_argument("-pf", "--print_frequency", help="ground truth file to be used for vector queries",
                        default=5)
    args = parser.parse_args()
    query_manager = QueryManager(args.connection_string, args.username, args.password, int(args.timeout),
                                 int(args.duration), args.template, args.use_sdk, args.query_type, args.query_file,
                                 args.groundtruth_file, args.validate_vector_query_results, args.distance_algo,
                                 args.bucket_list, args.use_tls, args.capella, args.skip_default,
                                 args.num_groundtruth_vectors, args.num_query_vectors)
    try:
        if args.action == "run_query_workload":
            query_manager.run_query_workload(int(args.num_concurrent_queries), int(args.refresh_duration))
            if args.validate_vector_query_results:
                query_manager.print_recall_stats()
        elif args.action == "poll_for_failed_queries":
            query_manager.poll_for_failed_queries()
        elif args.action == "cancel_random_queries":
            query_manager.cancel_random_queries(int(args.num_concurrent_queries))
        elif args.action == "fetch_active_requests":
            query_manager.fetch_columnar_active_requests()
        else:
            raise Exception("Actions allowed - run_query_workload | poll_for_failed_queries | cancel_random_queries")
    finally:
        query_error_resp_dict = query_manager.get_query_errors_dict()
        if query_error_resp_dict:
            print("========================Queries that have ended in errors==============================================================")
            print(json.dumps(query_error_resp_dict, indent=4))
            raise Exception(f"A few queries have ended in errors")


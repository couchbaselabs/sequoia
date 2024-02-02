import base64
import copy
import json
import socket
import string
import sys
import threading
import os
from concurrent.futures import as_completed
from concurrent.futures.thread import ThreadPoolExecutor
from datetime import datetime
from http.client import RemoteDisconnected, IncompleteRead

from couchbase.cluster import Cluster, ClusterOptions, QueryOptions, ClusterTimeoutOptions
from couchbase.exceptions import CouchbaseException, QueryIndexAlreadyExistsException, TimeoutException
from couchbase.auth import PasswordAuthenticator
from couchbase.management.collections import *

from vectorloader.vectorloader import HDF5_FORMATTED_DATASETS, VectorDataset

import random
import argparse
import logging
import requests
import time
import httplib2
import json
import paramiko
import dns.resolver

## Constants

HOTEL_DS_SINGLE_FIELD = [
    {
        "name": "country",
        "type": "text",
        "is_nested_object": False,
        "field_code": "country",
        "queries": [
            {
                "disjuncts": [
                    {
                        "wildcard": "Jord*",
                        "field": "country"
                    },
                    {
                        "match": "Cape Verde",
                        "field": "country",
                        "fuzziness": 2,
                        "operator": "or"
                    }
                ]
            }],
        "flex_queries": ["country = \"Moldova\"",
                         "country = \"Cape Verde\"",
                         "country like \"Jord*\"",
                         "country like \"Jord*\" or country = \"Cape Verde\""
                         ]
    }
]


# Some constants
HOTEL_DS_FIELDS = [
    {
        "name": "country",
        "type": "text",
        "is_nested_object": False,
        "field_code": "country",
        "queries": [{
            "match": "Moldova",
            "field": "country",
            "fuzziness": 1,
            "operator": "and"
        },
            {
                "match": "Cape Verde",
                "field": "country",
                "fuzziness": 1,
                "operator": "or"
            },
            {
                "wildcard": "Jord*",
                "field": "country"
            },
            {
                "min": "Cape", "max": "United",
                "inclusive_min": True,
                "inclusive_max": True,
                "field": "country"
            },
            {
                "disjuncts": [
                    {
                        "wildcard": "Jord*",
                        "field": "country"
                    },
                    {
                        "match": "Cape Verde",
                        "field": "country",
                        "fuzziness": 2,
                        "operator": "or"
                    }
                ]
            }],
        "flex_queries": ["country = \"Moldova\"",
                         "country = \"Cape Verde\"",
                         "country like \"Jord*\"",
                         "country like \"Jord*\" or country = \"Cape Verde\""
                         ]
    },
    {
        "name": "free_parking",
        "type": "boolean",
        "is_nested_object": False,
        "field_code": "free_parking",
        "queries": [{
            "bool": True,
            "field": "free_parking"
        },
            {
                "bool": False,
                "field": "free_parking"
            }],
        "flex_queries": ["free_parking = False",
                         "free_parking = True"]
    },
    {
        "name": "price",
        "type": "number",
        "is_nested_object": False,
        "field_code": "price",
        "queries": [{
            "query": "849"
        },
            {
                "min": 1, "max": 1000,
                "inclusive_min": False,
                "inclusive_max": False,
                "field": "price"
            }],
        "flex_queries": ["price = 849",
                         "price > 1 and price < 1000"
                         ]
    },
    {
        "name": "public_likes",
        "type": "text",
        "is_nested_object": False,
        "field_code": "public_likes",
        "score_none": True,
        "queries": [{
            "match": "Daina Cassin",
            "field": "public_likes"
        },
            {
                "prefix": "Da",
                "field": "public_likes"
            },
            {
                "wildcard": "Dain*",
                "field": "public_likes"
            }],
        "flex_queries": ["public_likes = \"Daina Cassin\"",
                         "public_likes like \"Dain%\""
                         ]
    },
    {
        "name": "reviews.ratings.Overall",
        "type": "number",
        "is_nested_object": True,
        "field_code": "Overall",
        "queries": [{
            "query": "reviews.ratings.Overall:3"
        },
            {
                "min": 1, "max": 1000,
                "inclusive_min": False,
                "inclusive_max": False,
                "field": "reviews.ratings.Overall"
            }],
        "flex_queries": ["ANY v in reviews.ratings.Overall SATISFIES v = 3 END"]
    },
    {
        "name": "reviews.date",
        "type": "datetime",
        "is_nested_object": True,
        "field_code": "type",
        "queries": [{
            "start": "2001-10-09",
            "end": "2021-10-31",
            "inclusive_start": False,
            "inclusive_end": False,
            "field": "review.date"
        },
            {
                "start": "2020-12-10",
                "end": "2020-12-18",
                "inclusive_start": False,
                "inclusive_end": False,
                "field": "reviews.date"
            }],
        "flex_queries": ["ANY v in reviews.date SATISFIES v > \"2001-10-09\" and v < \"2020-12-18\" END"]
    }
]

VECTOR_DS_FIELDS = [
    {
        "name": "vector_data",
        "type": "vector",
        "is_nested_object": False,
        "field_code": "vector_data"
    },
    {
        "name": "sname",
        "type": "text",
        "is_nested_object": False,
        "field_code": "sname",
        "queries": [
            {
                "wildcard": "ab*",
                "field": "sname"
            },
            {
                "prefix": "pq",
                "field": "sname"
            }
        ]
    }
]

VECTOR_DS_SINGLE_FIELD = [
    {
        "name": "vector_data",
        "type": "vector",
        "is_nested_object": False,
        "field_code": "vector_data"
    }
]


NUM_WORKERS = 2  # Max number of worker threads to execute queries
FTS_PORT = 8094


class FTSIndexManager:

    def __init__(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("-n", "--node", help="Couchbase Server Node Address")
        parser.add_argument("-o", "--port", help="Couchbase Server Node Port")
        parser.add_argument("-c", "--capella", help="Set to True for Capella system tests run", default=False)
        parser.add_argument("-u", "--username", help="Couchbase Server Cluster Username")
        parser.add_argument("-p", "--password", help="Couchbase Server Cluster Password")
        parser.add_argument("-b", "--bucket", help="Bucket name on which indexes are to be created")
        parser.add_argument("-m", "--index_partition_map", help="Index partion map for create index",
                            default="1:1:20,2:2:6")
        parser.add_argument("-s", "--scale", help="scale for Index partion map for create index", default=1)
        parser.add_argument("-i", "--num_indexes", type=int,
                            help="Number of indexes to be created on collections for a bucket, if action = create_index. "
                                 "If action=drop_index, number of indexes to be dropped per collection of bucket")
        parser.add_argument("-d", "--dataset", help="Dataset to be used for the test. Choices are - hotel",
                            default="hotel")
        parser.add_argument("-sc", "--scope", help="Scope to create indexes on", default=None)
        parser.add_argument("-t", "--duration", type=int,
                            help="Duration for queries to be run for. 0 (default) is infinite",
                            default="0")
        parser.add_argument("-nq", "--num_queries_per_worker", type=int,
                            help="Number of FTS queries to be run by each worker thread",
                            default=10)
        parser.add_argument("--print_interval", type=int,
                            help="Interval to print query result summary. Default is 10 mins",
                            default="600")
        parser.add_argument("-tls", "--secure", type=bool, help="for secure pass true", default=None)
        parser.add_argument("--interval", type=int, default=60,
                            help="Interval between 2 create index calls when running in a loop")
        parser.add_argument("--timeout", type=int, default=0,
                            help="Timeout for create index loop. 0 (default) is infinite")
        parser.add_argument("-vt", "--validation_timeout", type=int, default=1200,
                            help="Timeout for item_count_check")
        parser.add_argument("-k", "--knn_value", type=int, default=3,
                            help="k value for knn queries")
        parser.add_argument("-a", "--action",
                            choices=["create_index", "create_index_from_map", "run_queries", "delete_all_indexes",
                                     "create_index_loop", "item_count_check", "active_queries_check", "run_flex_queries",
                                     "create_index_from_map_on_bucket", "create_index_for_each_collection",
                                     "run_queries_on_each_index","copy_docs_from_source_collection",
                                     "update_docs_on_all_collections", "run_knn_queries"],
                            help="Choose an action to be performed. Valid actions : create_index, run_queries, "
                                 "delete_all_indexes, create_index_loop, item_count_check",
                            default="create_index")

        args = parser.parse_args()
        self.log = logging.getLogger("ftsindexmanager")
        self.capella_run = args.capella
        self.node_addr = args.node
        self.node_port = args.port
        self.username = args.username
        self.password = args.password
        self.bucket_name = args.bucket
        self.num_indexes = args.num_indexes
        self.dataset = args.dataset
        self.action = args.action
        self.duration = args.duration
        self.print_interval = args.print_interval
        self.interval = args.interval
        self.secure = args.secure
        self.use_https = self.secure or self.capella_run
        self.timeout = args.timeout
        self.index_partition_map = args.index_partition_map
        self.scale = args.scale
        self.scope = args.scope
        self.num_queries_per_worker = args.num_queries_per_worker
        self.validation_timeout = args.validation_timeout
        self.knn_value = args.knn_value

        self.idx_def_templates = HOTEL_DS_FIELDS
        if self.use_https:
            self.fts_port = 18094
            self.node_port = 18091
            self.protocol = "https"
            if self.capella_run:
                self.rest_url = self.fetch_rest_url(self.node_addr)
                if "svc-d-node" in self.rest_url:
                    self.rest_url = self.get_fts_node_addr()
            else:
                self.rest_url = self.node_addr
        else:
            self.fts_port = 8094
            self.node_port = 8091
            self.protocol = "http"
            self.url = "{}://".format(self.protocol) + self.node_addr + ":" + str(self.node_port)
            self.rest_url = self.node_addr
        # If there are more datasets supported, this can be expanded.
        if self.dataset == "hotel":
            self.idx_def_templates = HOTEL_DS_FIELDS
        elif self.dataset == "hotel_single_field":
            self.idx_def_templates = copy.deepcopy(HOTEL_DS_SINGLE_FIELD)
        elif self.dataset == "siftsmall":
            self.idx_def_templates = copy.deepcopy(VECTOR_DS_SINGLE_FIELD)
        else:
            self.idx_def_templates = copy.deepcopy(VECTOR_DS_FIELDS)

        self.knn_query = {
            "query": {
                "match_none": {}
            },
            "explain": True,
            "fields": ["*"],
            "knn": [
                {
                    "field": "vector_data",
                    "k": self.knn_value,
                    "vector": []
                }
            ]
        }

        if self.action == "run_knn_and_fts_queries":
            self.knn_query["query"] = random.choice(VECTOR_DS_FIELDS[1]["queries"])

            # Initialize connections to the cluster
        count = 0
        while True:
            try:
                #self.cb_admin = Admin(self.username, self.password, self.node_addr, self.node_port)
                #self.cb_coll_mgr = CollectionManager(self.cb_admin, self.bucket_name)
                options = ClusterOptions(PasswordAuthenticator(self.username, self.password))
                if self.use_https:
                    self.log.info("This is Capella run.")
                    self.cluster = Cluster('couchbases://' + self.node_addr + '?ssl=no_verify',
                                           options)
                else:
                    self.log.info("This is a Server run.")
                    self.cluster = Cluster('couchbase://{0}'.format(self.node_addr),
                                           options)
                self.cb = self.cluster.bucket(self.bucket_name)
                break
            except Exception as Ex:
                print(str(Ex))
                count+=1
                if count == 5:
                    raise

        self.cluster.search_indexes()

        # Logging configuration
        self.log.setLevel(logging.INFO)
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        ch.setFormatter(formatter)
        self.log.addHandler(ch)
        timestamp = str(datetime.now().strftime('%Y%m%dT_%H%M%S'))
        fh = logging.FileHandler("./ftsindexmanager-{0}.log".format(timestamp))
        fh.setFormatter(formatter)
        self.log.addHandler(fh)

        # Set max number of replica for the test. For that, fetch the number of indexer nodes in the cluster.
        self.max_num_replica = 0
        self.max_num_partitions = 20
        self.set_max_num_replica()

    def fetch_rest_url(self, url):
        """
        meant to find the srv record for Capella runs
        """
        self.log.info("This is a Capella run. Finding the srv domain for {}".format(url))
        srv_info = {}
        srv_records = dns.resolver.query('_couchbases._tcp.' + url, 'SRV')
        for srv in srv_records:
            srv_info['host'] = str(srv.target).rstrip('.')
            srv_info['port'] = srv.port
        self.log.info("This is a Capella run. Srv info {}".format(srv_info))
        return srv_info['host']

    def get_fts_node_addr(self):
        cluster_url = self.protocol + "://" + self.rest_url + ":" + str(self.node_port) + "/pools/default"
        node_map = []

        # Get map of nodes in the cluster
        response = requests.get(cluster_url, auth=(
            self.username, self.password), verify=False, )

        if (response.ok):
            response = json.loads(response.text)

            for node in response["nodes"]:
                if "svc-qs-node" in node["hostname"] or "svc-s-node" in node["hostname"]:
                    return node["hostname"][:-5]

    def get_all_collections(self):
        """
        Fetch list of all collections for the given bucket
        """
        cb_scopes = self.cb.collections().get_all_scopes()

        keyspace_name_list = []
        for scope in cb_scopes:
            if scope.name != "_system":
                for coll in scope.collections:
                    keyspace_name_list.append(scope.name + "." + coll.name)
        return (keyspace_name_list)

    """
    Fetch list of all scopes that have multiple collections
    """

    def get_all_scopes_with_multiple_collections(self):
        cb_scopes = self.cb.collections().get_all_scopes()
        print(cb_scopes)

        multi_coll_scopes = []

        for scope in cb_scopes:
            if scope.name != "_system":
                scope_obj = {}
                collections = []
                for coll in scope.collections:
                    collections.append(scope.name + "." + coll.name)
                if len(collections) > 1:
                    scope_obj[scope.name] = collections
                    multi_coll_scopes.append(scope_obj)
        return multi_coll_scopes

    def active_queries_check(self):
        while True:
            index_list = self.get_fts_index_list()
            for index_name in index_list:
                self.log_active_queries(index_name)

    def run_flex_queries(self):
        threads = []
        queries_run = 0
        queries_passed = 0
        queries_failed = 0
        with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
            # Establish timeout. If timeout > 0, run in infinite loop
            end_time = 0
            print_time = 0
            if self.duration > 0:
                end_time = time.time() + self.duration

            if self.print_interval > 0:
                print_time = time.time() + self.print_interval

            while True:
                random.seed(datetime.now())
                for i in range(self.num_queries_per_worker):
                    threads.append(executor.submit(self.generate_and_run_flex_query))
                    time.sleep(5)
                try:
                    for task in as_completed(threads):
                        result = task.result()
                        queries_run += 1
                        if result:
                            queries_passed += 1
                        else:
                            queries_failed += 1
                except Exception as e:
                    self.log.info(str(e))
                    queries_failed += 1

                # Print result summary if the print interval has passed
                if self.print_interval > 0 and time.time() > print_time:
                    self.log.info(
                        "======== Queries Run = {0} | Queries Passed = {1} | Queries Failed = {2} ========".format(
                            queries_run, queries_passed, queries_failed))
                    # Set next time to print result summary
                    print_time = time.time() + self.print_interval

                # Exit if timed out
                if self.duration > 0 and time.time() > end_time:
                    break

                # Wait for 1 min before submitting next set of threads
                alive_threads = len(threading.enumerate())
                if alive_threads > 5:
                    self.log.info("Waiting for {0} threads to complete...".format(len(threads)))
                    time.sleep(60)

    def log_active_queries(self, index_name):
        try:
            status, content, response = self.http_request(self.rest_url, self.fts_port,
                                                          "/api/query/index/{0}".format(index_name))
            self.log.info("status {0}, content {1}".format(status, content))
        except Exception as e:
            self.log.info(str(e))

    """
    Item Count Check
    1. Get all fts index names
    2. for each index
        a. extract items_count for index
        b. extact all collections index created on
        c. Run a count(*) query against all the collection to get the KV item count and add them
        d. Compare result from a & c and raiseException if not matching
    """

    def item_count_check(self):
        stat_time = time.time()
        end_time = stat_time + self.validation_timeout
        indexes_validated = []
        errors = []
        while time.time() < end_time:
            index_list = self.get_fts_index_list()
            if len(index_list) == len(indexes_validated):
                break
            errors = []

            for index_name in index_list:
                if index_name not in indexes_validated:
                    index_item_count = self.get_fts_index_doc_count(index_name)
                    all_index_col_count = self.get_fts_index_collections_count(index_name)
                    self.log.info(f'{index_name} : index_count : {index_item_count}, all_index_col_count : {all_index_col_count}')
                    if all_index_col_count is None:
                        indexes_validated.append(index_name)
                        break
                    if int(index_item_count) != int(all_index_col_count):
                        errors_obj = {"type": "item_count_check_failed", "index_name": index_name,
                                      "index_item_count": index_item_count, "all_index_col_count": all_index_col_count}
                        errors.append(errors_obj)
                    else:
                        indexes_validated.append(index_name)

            if len(errors) > 0:
                self.log.info("There were errors in the item count check phase - \n{0}".format(errors))
            else:
                self.log.info("Item check count passed. No discrepancies seen.")

        if len(errors) > 0:
            raise Exception("There were errors in the item count check phase - \n{0}".format(errors))
        else:
            self.log.info("Item check count passed. No discrepancies seen.")

    def create_fts_indexes_from_map_for_bucket(self):
        coll_list = self.get_all_collections()
        multi_coll_scopes = self.get_all_scopes_with_multiple_collections()
        partition_map_list = self.index_partition_map.split(",")
        for index_map in partition_map_list:
            num_indexes, num_replicas, num_partitions = index_map.split(":")
            num_indexes = int(self.scale) * int(num_indexes)
            for i in range(num_indexes):
                random.seed(datetime.now())
                collections = []
                if len(multi_coll_scopes) > 0:
                    # Select if to create single collection index or multi-collection (25% chance for multi collection idx)
                    index_type = random.choice(["single", "single", "single", "multi"])
                else:
                    index_type = "single"

                if index_type == "single":
                    collections.append(random.choice(coll_list))
                else:
                    # Select a scope with multiple collections first
                    scope_obj = random.choice(multi_coll_scopes)
                    scope_name = list(scope_obj.keys())[0]
                    num_coll = len(scope_obj[scope_name])
                    # Now randomly select a subset of random number collections from that scope
                    collections = random.sample(population=scope_obj[scope_name], k=random.randint(1, num_coll))

                self.log.info("===== Creating {1} FTS index on {0} =====".format(collections, index_type))
                status, content, response, idx_name = self.create_fts_index_on_collections(collections,
                                                                                           num_replica=int(num_replicas),
                                                                                           num_partitions=int(num_partitions))

                if not status:
                    self.log.info("Content = {0} \nResponse = {1}".format(content, response))
                    self.log.info("Index creation on {0} did not succeed. Pls check logs.".format(collections))

                # Remove the scope or collection on which the index was created
                if index_type == "single":
                    coll_list.remove(collections[0])
                else:
                    multi_coll_scopes.remove(scope_obj)

            ### TO - DO
            # Validate if all indexes have been created
            self.get_fts_index_list()

    def create_fts_indexes_from_map_on_bucket(self):
        partition_map_list = self.index_partition_map.split(",")
        for index_map in partition_map_list:
            num_indexes, num_replicas, num_partitions = index_map.split(":")
            num_indexes = int(self.scale) * int(num_indexes)
            for i in range(num_indexes):
                random.seed(datetime.now())

                self.log.info("===== Creating FTS index on {0} =====".format(self.bucket_name))
                status, content, response, idx_name = self.create_fts_index_on_bucket(num_replica=int(num_replicas),
                                                                                      num_partitions=int(num_partitions))

                if not status:
                    self.log.info("Content = {0} \nResponse = {1}".format(content, response))
                    self.log.info("Index creation on {0} did not succeed. Pls check logs.".format(self.bucket_name))

    def create_fts_index_for_each_collection(self):
        coll_list = self.get_all_collections()
        print(coll_list)
        coll_list.remove("_default._default")
        count = 0
        for coll in coll_list:
            print(coll)
            if self.scope:
                if self.scope+"." not in coll:
                    continue
            collections = [coll]
            self.log.info("===== Creating {1} FTS index on {0} =====".format(collections, "single"))
            status, content, response, idx_name = self.create_fts_index_on_collections(collections,
                                                                                       num_replica=0,
                                                                                       num_partitions=1,
                                                                                       count=count)

            if not status:
                self.log.info("Content = {0} \nResponse = {1}".format(content, response))
                self.log.info("Index creation on {0} did not succeed. Pls check logs.".format(collections))
            count += 1

    """
    Create n number of indexes for the specified bucket. These indexes could be on a single or multiple collections
    """

    def create_fts_indexes_for_bucket(self):
        coll_list = self.get_all_collections()
        multi_coll_scopes = self.get_all_scopes_with_multiple_collections()
        for i in range(0, self.num_indexes):
            random.seed(datetime.now())
            collections = []
            if len(multi_coll_scopes) > 0:
                # Select if to create single collection index or multi-collection (25% chance for multi collection idx)
                index_type = random.choice(["single", "single", "single", "multi"])
            else:
                index_type = "single"

            if index_type == "single":
                collections.append(random.choice(coll_list))
            else:
                # Select a scope with multiple collections first
                scope_obj = random.choice(multi_coll_scopes)
                scope_name = list(scope_obj.keys())[0]
                num_coll = len(scope_obj[scope_name])
                # Now randomly select a subset of random number collections from that scope
                collections = random.sample(population=scope_obj[scope_name], k=random.randint(1, num_coll))

            self.log.info("===== Creating {1} FTS index on {0} =====".format(collections, index_type))
            status, content, response, idx_name = self.create_fts_index_on_collections(collections)

            if not status:
                self.log.info("Content = {0} \nResponse = {1}".format(content, response))
                self.log.info("Index creation on {0} did not succeed. Pls check logs.".format(collections))

            # Remove the scope or collection on which the index was created
            if index_type == "single":
                coll_list.remove(collections[0])
            else:
                multi_coll_scopes.remove(scope_obj)

        ### TO - DO
        # Validate if all indexes have been created
        self.get_fts_index_list()

    """
        Create n number of indexes for the specified bucket. These indexes could be on a single or multiple collections
        """

    def create_fts_indexes_in_a_loop(self, timeout, interval):
        # Establish timeout. If timeout > 0, run in infinite loop
        end_time = 0
        if timeout > 0:
            end_time = time.time() + timeout
        count = 0
        while True:
            try:

                coll_list = self.get_all_collections()
                multi_coll_scopes = self.get_all_scopes_with_multiple_collections()

                coll_list = list(filter(lambda a: "_default" not in a, coll_list))
                multi_coll_scopes = list(filter(lambda a: "_default" not in a, multi_coll_scopes))

                collections = []
                random.seed(datetime.now())
                if len(multi_coll_scopes) > 0:
                    # Select if to create single collection index or multi-collection (25% chance for multi collection idx)
                    index_type = random.choice(["single", "single", "single", "multi"])
                else:
                    index_type = "single"

                if index_type == "single":
                    collections.append(random.choice(coll_list))
                else:
                    # Select a scope with multiple collections first
                    scope_obj = random.choice(multi_coll_scopes)
                    scope_name = list(scope_obj.keys())[0]
                    num_coll = len(scope_obj[scope_name])
                    # Now randomly select a subset of random number collections from that scope
                    collections = random.sample(population=scope_obj[scope_name], k=random.randint(1, num_coll))

                self.log.info("===== Creating {1} FTS index on {0} =====".format(collections, index_type))
                status, content, response, idx_name = self.create_fts_index_on_collections(collections, count)

                if not status:
                    self.log.info("Content = {0} \nResponse = {1}".format(content, response))
                    self.log.info("Index creation on {0} did not succeed. Pls check logs.".format(collections))
                    #command = f'yum install tcpdump -y;timeout 600 tcpdump -W 1 -G 300 -w tcp_dump_file_{idx_name}.pcap -s 0 port 8094'
                    #self.execute_command(command, self.node_addr, "root", "couchbase")
                else:
                    self.log.info(f'Index creation on {idx_name} succeeded. Content = {content}, Response = {response}')

                time.sleep(240)
                cur_indexes = self.get_fts_index_list()
                if idx_name in cur_indexes:
                    self.log.info(f'Deleting index {idx_name}')
                    uri = "/api/index/" + idx_name
                    status, content, response = self.http_request(self.rest_url, self.fts_port, uri, method="DELETE")
                    if not status:
                        self.log.info("Status : {0} \nResponse : {1} \nContent : {2}".format(status, response, content))
                        self.log.info("Index {0} not deleted".format(idx_name))

                # Exit if timed out
                if timeout > 0 and time.time() > end_time:
                    break
            except Exception as e:
                self.log.info(str(e))
            count += 1

            # Wait for the interval before doing the next CRUD operation
            time.sleep(interval)

    def create_fts_indexes_in_a_loop_on_bucket(self, timeout, interval):
        # Establish timeout. If timeout > 0, run in infinite loop
        end_time = 0
        if timeout > 0:
            end_time = time.time() + timeout
        count = 0
        while True:
            status, content, response, idx_name = self.create_fts_index_on_bucket(count)

            if not status:
                self.log.info("Content = {0} \nResponse = {1}".format(content, response))
                self.log.info("Index creation on {0} did not succeed. Pls check logs.".format(self.bucket_name))
                #command = f'yum install tcpdump -y;timeout 600 tcpdump -W 1 -G 300 -w tcp_dump_file_{idx_name}.pcap -s 0 port 8094'
                #self.execute_command(command, self.node_addr, "root", "couchbase")
            else:
                self.log.info(f'Index creation on {idx_name} succeeded. Content = {content}, Response = {response}')

            time.sleep(240)
            cur_indexes = self.get_fts_index_list()
            if idx_name in cur_indexes:
                self.log.info(f'Deleting index {idx_name}')
                uri = "/api/index/" + idx_name
                status, content, response = self.http_request(self.rest_url, self.fts_port, uri, method="DELETE")
                if not status:
                    self.log.info("Status : {0} \nResponse : {1} \nContent : {2}".format(status, response, content))
                    self.log.info("Index {0} not deleted".format(idx_name))

            # Exit if timed out
            if timeout > 0 and time.time() > end_time:
                break
            count += 1

            # Wait for the interval before doing the next CRUD operation
            time.sleep(interval)

    def execute_command(self, command, hostname, ssh_username, ssh_password):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname, username=ssh_username, password=ssh_password,
                    timeout=120, banner_timeout=120)

        channel = ssh.get_transport().open_session()
        channel.get_pty()
        channel.settimeout(900)
        stdin = channel.makefile('wb')
        stdout = channel.makefile('rb')
        stderro = channel.makefile_stderr('rb')

        self.log.info(f'Running {command} on node {hostname}')
        channel.exec_command(command)
        data = channel.recv(1024)
        temp = ""
        while data:
            temp += str(data)
            data = channel.recv(1024)
        channel.close()
        stdin.close()

        output = []
        error = []
        for line in stdout.read().splitlines():
            if "No such file or directory" not in line:
                output.append(line)
        for line in stderro.read().splitlines():
            error.append(line)
        if temp:
            line = temp.splitlines()
            output.extend(line)
        stdout.close()
        stderro.close()

        ssh.close()
        return len(output), output, error

    """
    Create FTS indexes on a given bucket with collections
    1. Determine number of indexes to be created
    2. Select field dictionary based on the dataset
    3. Get input on number of indexes to be created
    4. For each index to be created, select between single and multi-collection index
    5. For each index, randomize the following :
       - single or multi-collection index
       - collection(s) on which the index has to be created
       - Fields from the field dictionary
       - num replica
       - num partitions
    6. Create a index definition payload based on the fields selected.
    7. Create index

    """

    def create_fts_index_on_collections(self, collections, count=None, num_replica=None, num_partitions=None):
        random.seed(datetime.now())
        # Randomly select fields to create the index on
        if self.dataset == "hotel":
            ds_fields = copy.deepcopy(HOTEL_DS_FIELDS)
        elif self.dataset == "hotel_single_field":
            ds_fields = copy.deepcopy(HOTEL_DS_SINGLE_FIELD)
        elif self.dataset == "siftsmall":
            ds_fields = copy.deepcopy(VECTOR_DS_SINGLE_FIELD)
        else:
            ds_fields = copy.deepcopy(VECTOR_DS_FIELDS)

        if ds_fields == VECTOR_DS_FIELDS:
            num_fields = len(ds_fields)
        else:
            num_fields = random.randint(1, len(ds_fields))
        index_fields = []
        for i in range(num_fields):
            field = random.choice(ds_fields)
            ds_fields.remove(field)
            index_fields.append(field)

        self.log.debug("***********  Fields selected for index : {0}".format(index_fields))

        # Randomly choose number of partitions and replicas
        if not num_partitions:
            num_partitions = random.randint(2, self.max_num_partitions)
        if not num_replica and num_replica != 0:
            num_replica = random.randint(0, self.max_num_replica)

        # Generate index name. Index names will also have field codes so that the query runner can decode the fields used in the index.
        for i in range(5):
            idx_name = "bucket_"+self.bucket_name+"_idx_" + ''.join(random.choice(string.ascii_lowercase) for i in range(5))
            if count:
                idx_name += "_" + str(count)
            for field in index_fields:
                idx_name += "-" + field["field_code"]
            cur_indexes = self.get_fts_index_list()
            if idx_name not in cur_indexes:
                break

        self.log.info("Creating FTS index {0} on {1} with {2} replicas and {3} partitions".format(idx_name, collections,
                                                                                                  num_replica,
                                                                                                  num_partitions))

        # Generate the index definition payload
        # Index common properties
        index_def_dict = {}
        index_def_dict["type"] = "fulltext-index"
        index_def_dict["name"] = idx_name
        index_def_dict["sourceType"] = "gocbcore"
        index_def_dict["sourceName"] = self.bucket_name
        index_def_dict["sourceParams"] = {}
        index_def_dict["planParams"] = {}
        index_def_dict["planParams"]["maxPartitionsPerPIndex"] = 512
        index_def_dict["planParams"]["indexPartitions"] = num_partitions
        if num_replica > 0:
            index_def_dict["planParams"]["numReplicas"] = num_replica

        index_def_dict["store"] = {}
        index_def_dict["store"]["indexType"] = "scorch"
        index_def_dict["params"] = {}
        index_def_dict["params"]["doc_config"] = {}
        index_def_dict["params"]["doc_config"]["docid_prefix_delim"] = ""
        index_def_dict["params"]["doc_config"]["docid_regexp"] = ""
        index_def_dict["params"]["doc_config"]["mode"] = "scope.collection.type_field"
        index_def_dict["params"]["doc_config"]["type_field"] = "type"

        # Index mapping common properties
        index_def_dict["params"]["mapping"] = {}
        #index_def_dict["params"]["mapping"]["default_analyzer"] = "keyword"
        index_def_dict["params"]["mapping"]["default_datetime_parser"] = "dateTimeOptional"
        index_def_dict["params"]["mapping"]["default_field"] = "_all"
        index_def_dict["params"]["mapping"]["default_mapping"] = {}
        index_def_dict["params"]["mapping"]["default_mapping"]["dynamic"] = True
        index_def_dict["params"]["mapping"]["default_mapping"]["enabled"] = False
        index_def_dict["params"]["mapping"]["default_type"] = "_default"
        index_def_dict["params"]["mapping"]["docvalues_dynamic"] = True
        index_def_dict["params"]["mapping"]["index_dynamic"] = True
        index_def_dict["params"]["mapping"]["store_dynamic"] = False
        index_def_dict["params"]["mapping"]["type_field"] = "_type"
        index_def_dict["params"]["mapping"]["types"] = {}

        for collection in collections:
            # Index type mapping - 1 per collection
            index_def_dict["params"]["mapping"]["types"][collection] = {}
            index_def_dict["params"]["mapping"]["types"][collection]["dynamic"] = False
            index_def_dict["params"]["mapping"]["types"][collection]["enabled"] = True
            index_def_dict["params"]["mapping"]["types"][collection]["properties"] = {}

            # For each field selected to be indexed, add it to the type mapping
            for field in index_fields:
                if field["is_nested_object"] == False:
                    field_name = field["name"]
                else:
                    field_name_parts = field["name"].split(".")
                    field_name = field_name_parts[0]
                if field_name not in index_def_dict["params"]["mapping"]["types"][collection]["properties"]:
                    index_def_dict["params"]["mapping"]["types"][collection]["properties"][field_name] = {}
                    index_def_dict["params"]["mapping"]["types"][collection]["properties"][field_name][
                        "dynamic"] = False
                    index_def_dict["params"]["mapping"]["types"][collection]["properties"][field_name]["enabled"] = True
                else:
                    self.log.info("Field {0} already exists".format(field_name))

                if field["is_nested_object"] == False:
                    index_def_dict["params"]["mapping"]["types"][collection]["properties"][field_name]["fields"] = []

                    field_dict = {}
                    field_dict["index"] = True
                    field_dict["name"] = field["name"]
                    field_dict["type"] = field["type"]
                    if field["type"] == "vector":
                        if self.dataset == "siftsmall":
                            field_dict["dims"] = 128
                        else:
                            field_dict["dims"] = HDF5_FORMATTED_DATASETS[self.dataset]["dimension"]
                        if len(collections) > 1:
                            field_dict["similarity"] = "dot_product"
                        else:
                            field_dict["similarity"] = random.choice(["dot_product", "l2_norm"])
                    index_def_dict["params"]["mapping"]["types"][collection]["properties"][field_name]["fields"].append(
                        field_dict)

                else:
                    field_name_parts = field["name"].split(".")
                    mapping = {}

                    j = 1
                    while j < len(field_name_parts):

                        child_mapping = {}
                        child_mapping[field_name_parts[j]] = {}
                        child_mapping[field_name_parts[j]]["dynamic"] = False
                        child_mapping[field_name_parts[j]]["enabled"] = True

                        if j == len(field_name_parts) - 1:
                            child_mapping[field_name_parts[j]]["fields"] = []
                            field_dict = {}
                            field_dict["index"] = True
                            field_dict["name"] = field_name_parts[j]
                            field_dict["type"] = field["type"]
                            child_mapping[field_name_parts[j]]["fields"].append(field_dict)
                        else:
                            child_mapping[field_name_parts[j]]["properties"] = {}

                        if mapping == {}:
                            mapping = copy.deepcopy(child_mapping)
                        else:
                            if field_name_parts[j - 1] in mapping:
                                mapping[field_name_parts[j - 1]]["properties"] = child_mapping

                        j += 1

                    if "properties" not in index_def_dict["params"]["mapping"]["types"][collection]["properties"][
                        field_name]:
                        index_def_dict["params"]["mapping"]["types"][collection]["properties"][field_name][
                            "properties"] = {}
                        index_def_dict["params"]["mapping"]["types"][collection]["properties"][field_name][
                            "properties"] = mapping
                    else:
                        index_def_dict["params"]["mapping"]["types"][collection]["properties"][field_name][
                            "properties"].update(mapping)

        self.log.debug("Final index definition - \n{0}".format(index_def_dict))

        # Create FTS index via REST
        index_definition = json.dumps(index_def_dict)

        #check if collections exists
        all_collections = self.get_all_collections()
        for collection in collections:
            if collection not in all_collections:
                return False, "Seems like collections did not exist. So did not try to create index", "None"

        status, content, response = self.http_request(self.rest_url, self.fts_port, "/api/index/{0}".format(idx_name),
                                                      method="PUT", body=index_definition)

        return status, content, response, idx_name

    def create_fts_index_on_bucket(self, count=None, num_replica=None, num_partitions=None, vector_field=None):
        random.seed(datetime.now())
        # Randomly select fields to create the index on
        if self.dataset == "hotel":
            ds_fields = copy.deepcopy(HOTEL_DS_FIELDS)
        elif self.dataset == "hotel_single_field":
            ds_fields = copy.deepcopy(HOTEL_DS_SINGLE_FIELD)
        elif self.dataset == "siftsmall":
            ds_fields = copy.deepcopy(VECTOR_DS_SINGLE_FIELD)
        else:
            ds_fields = copy.deepcopy(VECTOR_DS_FIELDS)

        num_fields = random.randint(1, len(ds_fields))
        index_fields = []
        for i in range(num_fields):
            field = random.choice(ds_fields)
            ds_fields.remove(field)
            index_fields.append(field)

        self.log.debug("***********  Fields selected for index : {0}".format(index_fields))

        # Randomly choose number of partitions and replicas
        if not num_partitions:
            num_partitions = random.randint(2, self.max_num_partitions)
        if not num_replica:
            num_replica = random.randint(0, self.max_num_replica)

        # Generate index name. Index names will also have field codes so that the query runner can decode the fields used in the index.
        for i in range(5):
            idx_name = "bucket_"+self.bucket_name+"_idx_" + ''.join(random.choice(string.ascii_lowercase) for i in range(5))
            for field in index_fields:
                idx_name += "-" + field["field_code"]
            if count:
                idx_name += "_" + str(count)
            cur_indexes = self.get_fts_index_list()
            if idx_name not in cur_indexes:
                break

        self.log.info("Creating FTS index {0} on {1} with {2} replicas and {3} partitions".format(idx_name, self.bucket_name,
                                                                                                  num_replica,
                                                                                                  num_partitions))

        # Generate the index definition payload
        # Index common properties
        index_def_dict = {}
        index_def_dict["type"] = "fulltext-index"
        index_def_dict["name"] = idx_name
        index_def_dict["sourceType"] = "couchbase"
        index_def_dict["sourceName"] = self.bucket_name
        index_def_dict["planParams"] = {}
        index_def_dict["planParams"]["maxPartitionsPerPIndex"] = 512
        index_def_dict["planParams"]["indexPartitions"] = num_partitions
        if num_replica > 0:
            index_def_dict["planParams"]["numReplicas"] = num_replica

        index_def_dict["store"] = {}
        index_def_dict["store"]["indexType"] = "scorch"
        index_def_dict["params"] = {}
        index_def_dict["params"]["doc_config"] = {}
        index_def_dict["params"]["doc_config"]["docid_prefix_delim"] = ""
        index_def_dict["params"]["doc_config"]["docid_regexp"] = ""
        index_def_dict["params"]["doc_config"]["mode"] = "type_field"
        index_def_dict["params"]["doc_config"]["type_field"] = "type"

        # Index mapping common properties
        index_def_dict["params"]["mapping"] = {}
        index_def_dict["params"]["mapping"]["default_analyzer"] = "keyword"
        index_def_dict["params"]["mapping"]["default_datetime_parser"] = "dateTimeOptional"
        index_def_dict["params"]["mapping"]["default_field"] = "_all"
        index_def_dict["params"]["mapping"]["default_mapping"] = {}
        index_def_dict["params"]["mapping"]["default_mapping"]["dynamic"] = False
        index_def_dict["params"]["mapping"]["default_mapping"]["enabled"] = True
        index_def_dict["params"]["mapping"]["default_mapping"]["default_analyzer"] = "keyword"
        index_def_dict["params"]["mapping"]["default_mapping"]["properties"] = {}
        index_def_dict["params"]["mapping"]["default_type"] = "_default"
        index_def_dict["params"]["mapping"]["docvalues_dynamic"] = True
        index_def_dict["params"]["mapping"]["index_dynamic"] = True
        index_def_dict["params"]["mapping"]["store_dynamic"] = False

        for field in index_fields:
            if field["is_nested_object"] == False:
                field_name = field["name"]
            else:
                field_name_parts = field["name"].split(".")
                field_name = field_name_parts[0]
            if field_name not in index_def_dict["params"]["mapping"]["default_mapping"]["properties"]:
                index_def_dict["params"]["mapping"]["default_mapping"]["properties"][field_name] = {}
                index_def_dict["params"]["mapping"]["default_mapping"]["properties"][field_name][
                    "dynamic"] = False
                index_def_dict["params"]["mapping"]["default_mapping"]["properties"][field_name]["enabled"] = True
            else:
                self.log.info("Field {0} already exists".format(field_name))

            if field["is_nested_object"] == False:
                index_def_dict["params"]["mapping"]["default_mapping"]["properties"][field_name]["fields"] = []

                field_dict = {}
                field_dict["index"] = True
                field_dict["name"] = field["name"]
                field_dict["type"] = field["type"]
                index_def_dict["params"]["mapping"]["default_mapping"]["properties"][field_name]["fields"].append(
                    field_dict)

            else:
                field_name_parts = field["name"].split(".")
                mapping = {}

                j = 1
                while j < len(field_name_parts):

                    child_mapping = {}
                    child_mapping[field_name_parts[j]] = {}
                    child_mapping[field_name_parts[j]]["dynamic"] = False
                    child_mapping[field_name_parts[j]]["enabled"] = True

                    if j == len(field_name_parts) - 1:
                        child_mapping[field_name_parts[j]]["fields"] = []
                        field_dict = {}
                        field_dict["index"] = True
                        field_dict["name"] = field_name_parts[j]
                        field_dict["type"] = field["type"]
                        child_mapping[field_name_parts[j]]["fields"].append(field_dict)
                    else:
                        child_mapping[field_name_parts[j]]["properties"] = {}

                    if mapping == {}:
                        mapping = copy.deepcopy(child_mapping)
                    else:
                        if field_name_parts[j - 1] in mapping:
                            mapping[field_name_parts[j - 1]]["properties"] = child_mapping

                    j += 1

                if "properties" not in index_def_dict["params"]["mapping"]["default_mapping"]["properties"][
                    field_name]:
                    index_def_dict["params"]["mapping"]["default_mapping"]["properties"][field_name][
                        "properties"] = {}
                    index_def_dict["params"]["mapping"]["default_mapping"]["properties"][field_name][
                        "properties"] = mapping
                else:
                    index_def_dict["params"]["mapping"]["default_mapping"]["properties"][field_name][
                        "properties"].update(mapping)

        self.log.info("Final index definition - \n{0}".format(index_def_dict))

        # Create FTS index via REST
        index_definition = json.dumps(index_def_dict)

        status, content, response = self.http_request(self.rest_url, self.fts_port, "/api/index/{0}".format(idx_name),
                                                      method="PUT", body=index_definition)

        return status, content, response, idx_name

    """
    Retrieve list of FTS indexes in the cluster
    """

    def get_fts_index_list(self, bucket=None):
        index_names = []
        status, content, response = self.http_request(self.rest_url, self.fts_port, "/api/index")
        if status:
            try:
                index_names = list(content["indexDefs"]["indexDefs"].keys())
            # self.log.info("FTS indexes in cluster - \n : ".format(list(content["indexDefs"]["indexDefs"].keys())))
                if bucket:
                    index_names = list(filter(lambda a: bucket in a, index_names))
                self.log.info("FTS indexes in cluster - : \n{0}".format(index_names))
            except TypeError as err:
                self.log.info(str(err))
                index_names = []

        return index_names

    """
    Given index name, Retrieve item count in the index
    """
    def get_fts_index_doc_count(self, name):
        """ get number of docs indexed"""
        count = 0
        content = ""
        try:
            status, content, response = self.http_request(self.rest_url, self.fts_port, "/api/index/{0}/count".format(name))
            count = content['count']
        except TypeError as err:
            self.log.info(f'error: {err} while retrieving count for index {name}, content : {content}')
        return count

    def get_fts_index_collections_count(self, name):
        """ get number of docs indexed"""
        status, content, response = self.http_request(self.rest_url, self.fts_port, "/api/index/{0}".format(name))
        types = content["indexDef"]["params"]["mapping"]["types"]
        bucket_name = content["indexDef"]["sourceName"]
        collection_list = list(types.keys())
        tot_index_col_count = 0
        for col in collection_list:
            try:
                scope, collection = col.split(".")
                keyspace_name_for_query = "`" + bucket_name + "`.`" + scope + "`.`" + collection + "`"
            except Exception as e:
                self.log.info(f'Could not get scope and collection for {col}')
                #keyspace_name_for_query = "`" + bucket_name + "`.`_default`.`_default`"
                return None


            # Get Collection item count from KV via N1QL
            kv_item_count_query = "select raw count(*) from {0};".format(keyspace_name_for_query)
            try:
                status, results, queryResult = self._execute_query(kv_item_count_query)
                if status is not None:
                    for result in results:
                        self.log.debug(result)
                        tot_index_col_count += result
                else:
                    self.log.info("Got an error retrieving stat from query via n1ql with query - {0}. Status : {1} ".
                                  format(kv_item_count_query, status))
            except Exception as e:
                self.log.info("Got an error retrieving stat from query via n1ql with query - {0}. Exception : {1} ".
                              format(kv_item_count_query, str(e)))

        return tot_index_col_count


    """
    Method to execute a query statement
    """

    def _execute_query(self, statement):
        status = None
        results = None
        queryResult = None
        nodelist = self.find_nodes_with_service(self.get_services_map(), "n1ql")
        if self.use_https:
            query_node = Cluster('couchbases://{0}'.format(self.node_addr),
                                           ClusterOptions(PasswordAuthenticator(self.username, self.password)))
        else:
            query_node = Cluster('couchbase://{0}'.format(nodelist[0]),
                               ClusterOptions(PasswordAuthenticator(self.username, self.password)))

        try:
            timeout = timedelta(minutes=5)
            queryResult = query_node.query(statement, QueryOptions(timeout=timeout))
            try:
                status = queryResult.metadata().status()
                results = queryResult.rows()
            except:
                self.log.error("Unexpected error :", sys.exc_info()[0])
                self.log.info("Query didnt return status or results")
                pass


        except CouchbaseException as qerr:
            self.log.debug("qerr")
            self.log.error(qerr)
        except HTTPException as herr:
            self.log.debug("herr")
            self.log.error(herr)
        except QueryIndexAlreadyExistsException as qiaeerr:
            self.log.debug("qiaeerr")
            self.log.error(qiaeerr)
        except TimeoutException as terr:
            self.log.debug("terr")
            self.log.error(terr)
        except:
            self.log.error("Unexpected error :", sys.exc_info()[0])

        return status, results, queryResult

    """
    Delete all FTS indexes
    """

    def delete_all_indexes(self):
        index_names = self.get_fts_index_list()
        for index in index_names:
            if "bucket_" + self.bucket_name + "_idx" in index:
                self.log.info(f'Deleting index {index}')
                uri = "/api/index/" + index
                status, content, response = self.http_request(self.rest_url, self.fts_port, uri, method="DELETE")
                if not status:
                    self.log.info("Status : {0} \nResponse : {1} \nContent : {2}".format(status, response, content))
                    self.log.info("Index {0} not deleted. Trying again".format(index))

        index_names = self.get_fts_index_list()

        for index in index_names:
            if "bucket_" + self.bucket_name + "_idx" in index:
                raise Exception("Indexes for the bucket {0} not deleted".format(self.bucket_name))

    """
    Retrieve fields for a given index
    """

    def get_index_fields(self, indexname):
        field_names = indexname.split("-")[1:]
        idx_fields_details = []

        for field in field_names:
            for ds_field in self.idx_def_templates:
                if field == ds_field["field_code"]:
                    idx_fields_details.append(ds_field)
                    break
                else:
                    pass

        return idx_fields_details

    """
    Runs FTS queries with multi-threading
    """

    def fts_query_runner(self):

        threads = []
        queries_run = 0
        queries_passed = 0
        queries_failed = 0
        with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
            # Establish timeout. If timeout > 0, run in infinite loop
            end_time = 0
            print_time = 0
            if self.duration > 0:
                end_time = time.time() + self.duration

            if self.print_interval > 0:
                print_time = time.time() + self.print_interval

            while True:
                random.seed(datetime.now())
                for i in range(self.num_queries_per_worker):
                    threads.append(executor.submit(self.generate_and_run_fts_query))
                    time.sleep(5)

                for task in as_completed(threads):
                    result = task.result()
                    queries_run += 1
                    if result:
                        queries_passed += 1
                    else:
                        queries_failed += 1

                # Print result summary if the print interval has passed
                if self.print_interval > 0 and time.time() > print_time:
                    self.log.info(
                        "======== Queries Run = {0} | Queries Passed = {1} | Queries Failed = {2} ========".format(
                            queries_run, queries_passed, queries_failed))
                    # Set next time to print result summary
                    print_time = time.time() + self.print_interval

                # Exit if timed out
                if self.duration > 0 and time.time() > end_time:
                    break

                # Wait for 1 min before submitting next set of threads
                alive_threads = len(threading.enumerate())
                if alive_threads > 5:
                    self.log.info("Waiting for {0} threads to complete...".format(len(threads)))
                    time.sleep(60)

    def fts_query_runner_on_each_index(self):

        threads = []
        queries_run = 0
        queries_passed = 0
        queries_failed = 0
        with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
            # Establish timeout. If timeout > 0, run in infinite loop
            end_time = 0
            print_time = 0
            if self.duration > 0:
                end_time = time.time() + self.duration

            if self.print_interval > 0:
                print_time = time.time() + self.print_interval

            index_names = self.get_fts_index_list(self.bucket_name)
            for index_name in index_names:
                random.seed(datetime.now())
                for i in range(self.num_queries_per_worker):
                    threads.append(executor.submit(self.generate_and_run_fts_query, index_name=index_name))
                    time.sleep(5)

                for task in as_completed(threads):
                    result = task.result()
                    queries_run += 1
                    if result:
                        queries_passed += 1
                    else:
                        queries_failed += 1

                # Print result summary if the print interval has passed
                if self.print_interval > 0 and time.time() > print_time:
                    self.log.info(
                        "======== Queries Run = {0} | Queries Passed = {1} | Queries Failed = {2} ========".format(
                            queries_run, queries_passed, queries_failed))
                    # Set next time to print result summary
                    print_time = time.time() + self.print_interval

                # Exit if timed out
                if self.duration > 0 and time.time() > end_time:
                    break

                # Wait for 1 min before submitting next set of threads
                alive_threads = len(threading.enumerate())
                if alive_threads > 5:
                    self.log.info("Waiting for {0} threads to complete...".format(len(threads)))
                    time.sleep(60)

    """
    Run Flex queries on random index with random fields
    """

    def generate_and_run_flex_query(self):
        index_names = self.get_fts_index_list(self.bucket_name)

        try:
            index_name = random.choice(index_names)
        except Exception as e:
            self.log.info("Exception fetching index names : {0} - {1}".format(index_names, str(e)))
            return False
        if index_name:
            index_fields = self.get_index_fields(index_name)
            try:
                index_field = random.choice(index_fields)
            except Exception as e:
                self.log.info(
                    "Exception fetching index fields {0} for index  : {1} - {2}".format(index_fields, index_name,
                                                                                        str(e)))
                return False
        else:
            self.log.info("Index name selected for running query is empty. Discarding attempt to run query")
            return False
        query = random.choice(index_field["flex_queries"])
        self.log.info("--------------- Running query {1} on {0} ---------------".format(index_name, query))
        status = self.run_flex_query(index_name, query)

        try:
            if status:
                self.log.info(f'Index name: {index_name}, Query: {query}, Status: {status}')
        except TypeError as terr:
            self.log.info(str(terr))
        except:
            self.log.error("Unexpected error :", sys.exc_info()[0])

        return status

    """
    Run FTS queries on random index with random fields
    """

    def generate_and_run_fts_query(self, index_name=None):
        index_names = self.get_fts_index_list(self.bucket_name)

        try:
            if not index_name:
                index_name = random.choice(index_names)
        except Exception as e:
            self.log.info("Exception fetching index names : {0} - {1}".format(index_names, str(e)))
            return False
        if index_name:
            index_fields = self.get_index_fields(index_name)
            try:
                index_field = random.choice(index_fields)
            except Exception as e:
                self.log.info(
                    "Exception fetching index fields {0} for index  : {1} - {2}".format(index_fields, index_name,
                                                                                        str(e)))
                return False
        else:
            self.log.info("Index name selected for running query is empty. Discarding attempt to run query")
            return False
        self.log.info("--------------- Running query on {0} field {1} ---------------".format(index_name, index_field))
        query = random.choice(index_field["queries"])

        if "score_none" in index_field:
            status, content, response = self.run_fts_query(index_name, query, score_none=True)
        else:
            status, content, response = self.run_fts_query(index_name, query, score_none=False)

        try:
            if status:
                self.log.info(f'Index name: {index_name}, Query: {query}, Status: {status}, '
                              f'Response: {response["status"]}, '
                              f'Total Hits: {content["total_hits"]}, '
                              f'Result Status: {content["status"]}')
        except TypeError as terr:
            self.log.debug(str(terr))
            self.log.info("Content does not have total hits = {0}".format(content))
        except:
            self.log.error("Unexpected error :", sys.exc_info()[0])

        return status

    """
    Run single FTS query
    """

    def run_fts_query(self, index_name, query, score_none=False, knn=None):
        uri = "/api/index/" + index_name + "/query"

        body = {}
        body["explain"] = True
        #body["fields"] = ["*"]
        #body["highlight"] = {}
        body["query"] = query
        body["explain"] = random.choice([True, False])

        if score_none:
            body["score"] = "none"

        if knn:
            body["knn"] = knn

        # Randomize size (not more than 1000)
        size = random.randint(10, 20)

        # Randomize offset (from)
        offset = random.randint(0, 10000)

        body["size"] = size
        body["from"] = offset
        body["ctl"] = {"timeout": 120000}
        consistency_level = random.choice([True, False])
        if consistency_level:
            body["ctl"]["consistency"] = {
                "level": "at_plus"
            }

        self.log.info("URI : {0} body : {1}".format(uri, body))

        # Randomize FTS host on which the query has to be run for load distribution
        fts_node_list = self.find_nodes_with_service(self.get_services_map(), "fts")
        query_host = random.choice(fts_node_list)
        status, content, response = self.http_request(query_host, self.fts_port, uri, method="POST", body=json.dumps(body))

        return status, content, response

    """
    Run single Flex query
    """

    def run_flex_query(self, index_name, query):
        index_hint = "USE INDEX (USING FTS, USING GSI)"
        status, content, response = self.http_request(self.rest_url, self.fts_port, "/api/index/{0}".format(index_name))
        types = content["indexDef"]["params"]["mapping"]["types"]
        bucket_name = content["indexDef"]["sourceName"]
        collection_list = list(types.keys())
        collection_to_query = random.choice(collection_list)
        scope, collection = collection_to_query.split(".")
        keyspace_name_for_query = "`" + bucket_name + "`.`" + scope + "`.`" + collection + "`"

        flex_query = f'select meta().id from {keyspace_name_for_query} {index_hint} where {query} limit 1000'
        self.log.info(f'flex query: {flex_query}')
        try:
            status, results, queryResult = self._execute_query(flex_query)
            if status is not None:
                self.log.info(f'For {query}, Status: {status}, Length of results: {len(results)}')
            else:
                self.log.info("Got an error retrieving stat from query via n1ql with query - {0}. Status : {1} ".
                              format(flex_query, status))
        except Exception as e:
            self.log.info("Got an error retrieving stat from query via n1ql with query - {0}. Exception : {1} ".
                          format(flex_query, str(e)))

        return status

    def run_knn_queries(self):
        vector_index_names = self.get_fts_index_list(self.bucket_name)
        for index in vector_index_names:
            queries = self.get_query_vectors()
            for count, q in enumerate(queries):
                self.knn_query['knn'][0]['vector'] = q.tolist()
                self.run_fts_query(index_name=index, query=self.knn_query['query'], knn=self.knn_query['knn'])




    def get_query_vectors(self):
        ds = VectorDataset(self.dataset)
        use_hdf5_datasets = True
        if ds.dataset_name in ds.supported_sift_datasets:
            use_hdf5_datasets = False
        ds.extract_vectors_from_file(use_hdf5_datasets=use_hdf5_datasets, type_of_vec="query")
        print(f"First Query vector:{str(ds.query_vecs[0])}")
        return ds.query_vecs

    def copy_docs_source_collection(self, create_primary=True):
        #create primary index on bucket.scope_0.coll_0"
        source_keyspace = self.bucket_name + ".scope_0.coll_0"
        if create_primary:
            index_name = self.bucket_name + "_idx"
            prim_index_query = f"Create primary index {index_name} on {source_keyspace}"
            try:
                status, results, queryResult = self._execute_query(prim_index_query)
                if status is not None:
                    self.log.info(f'For {prim_index_query}, Status: {status}, Length of results: {len(results)}')
                else:
                    self.log.info("Got an error retrieving stat from query via n1ql with query - {0}. Status : {1} ".
                                  format(prim_index_query, status))
            except Exception as e:
                self.log.info("Got an error retrieving stat from query via n1ql with query - {0}. Exception : {1} ".
                              format(prim_index_query, str(e)))

        coll_list = self.get_all_collections()
        coll_list.remove("_default._default")
        coll_list.remove("scope_0.coll_0")
        for coll in coll_list:
            query = f'upsert into {self.bucket_name}.{coll} (key _k, value _v) select meta().id _k, _v from {source_keyspace} _v'
            self.log.info(f'query: {query}')
            try:
                status, results, queryResult = self._execute_query(query)
                if status is not None:
                    self.log.info(f'For {query}, Status: {status}, Length of results: {len(results)}')
                else:
                    self.log.info("Got an error retrieving stat from query via n1ql with query - {0}. Status : {1} ".
                                  format(query, status))
            except Exception as e:
                self.log.info("Got an error retrieving stat from query via n1ql with query - {0}. Exception : {1} ".
                              format(query, str(e)))

    def update_docs(self):
        source_keyspace = "bucket1.scope_0.coll_0"
        query = f'UPDATE {source_keyspace} set country="United States" where country="France"'
        self.log.info(f'query: {query}')
        try:
            status, results, queryResult = self._execute_query(query)
            if status is not None:
                self.log.info(f'For {query}, Status: {status}, Length of results: {len(results)}')
            else:
                self.log.info("Got an error retrieving stat from query via n1ql with query - {0}. Status : {1} ".
                              format(query, status))
        except Exception as e:
            self.log.info("Got an error retrieving stat from query via n1ql with query - {0}. Exception : {1} ".
                          format(query, str(e)))

        self.copy_docs_source_collection(create_primary=False)

    """
    Generic method to perform a REST call
    """

    def http_request(self, host, port, uri, method="GET", body=None):
        credentials = '{}:{}'.format(self.username, self.password)
        authorization = base64.encodebytes(credentials.encode('utf-8'))
        authorization = authorization.decode('utf-8').rstrip('\n')

        headers = {'Content-Type': 'application/json',
                   'Authorization': 'Basic %s' % authorization,
                   'Accept': '*/*',
                   'Cache-Control': 'no-cache'}

        url = self.protocol+"://" + host + ":" + str(port) + uri
        http = httplib2.Http(timeout=600, disable_ssl_certificate_validation=True)
        http.add_credentials(self.username, self.password)
        print(body)
        try:
            response, content = http.request(uri=url, method=method, headers=headers, body=body)

        except (RemoteDisconnected, httplib2.HttpLib2Error, socket.error, IncompleteRead) as ex:
            self.log.info(f'{url}, {body}, {ex}')
            return False, None, None

        if response['status'] in ['200', '201', '202']:
            return True, json.loads(content), response
        else:
            return False, content, response

    """
    Determine number of fts nodes in the cluster and set max num replica accordingly.
    """

    def set_max_num_replica(self):
        nodelist = self.find_nodes_with_service(self.get_services_map(), "fts")
        self.max_num_replica = len(nodelist) - 1  # Max num replica = number of fts nodes in cluster - 1
        if self.max_num_replica > 3:
            self.max_num_replica = 3
        self.log.info("Setting Max Replica for this test to : {0}".format(self.max_num_replica))

    """
    Populate the service map for all nodes in the cluster.
    """

    def get_services_map(self):
        cluster_url = self.protocol + "://" + self.rest_url + ":" + str(self.node_port) + "/pools/default"
        node_map = []

        # Get map of nodes in the cluster
        response = requests.get(cluster_url, auth=(
            self.username, self.password), verify=False, )

        if (response.ok):
            response = json.loads(response.text)

            for node in response["nodes"]:
                clusternode = {}
                clusternode["hostname"] = node["hostname"].replace(":8091", "")
                clusternode["services"] = node["services"]
                clusternode["status"] = node["status"]
                node_map.append(clusternode)
        else:
            response.raise_for_status()

        return node_map

    """
    From the service map, find all nodes running the specified service and return the node list.
    """

    def find_nodes_with_service(self, node_map, service):
        nodelist = []
        for node in node_map:
            if service == "all":
                nodelist.append(node["hostname"])
            else:
                if service in node["services"]:
                    nodelist.append(node["hostname"])
        return nodelist


"""
Main method
TODO : 1. Validation to check if indexes are created successfully
       2. Build all deferred indexes mode
       3. Wait for all indexes to be built mode
       4. Drop some indexes mode
"""
if __name__ == '__main__':
    ftsIndexMgr = FTSIndexManager()

    if ftsIndexMgr.action == "create_index":
        ftsIndexMgr.create_fts_indexes_for_bucket()
    elif ftsIndexMgr.action == "create_index_from_map":
        ftsIndexMgr.create_fts_indexes_from_map_for_bucket()
    elif ftsIndexMgr.action == "create_index_from_map_on_bucket":
        ftsIndexMgr.create_fts_indexes_from_map_on_bucket()
    elif ftsIndexMgr.action == "create_index_for_each_collection":
        ftsIndexMgr.create_fts_index_for_each_collection()
    elif ftsIndexMgr.action == "run_queries":
        ftsIndexMgr.fts_query_runner()
    elif ftsIndexMgr.action == "run_queries_on_each_index":
        ftsIndexMgr.fts_query_runner_on_each_index()
    elif ftsIndexMgr.action == "delete_all_indexes":
        ftsIndexMgr.delete_all_indexes()
    elif ftsIndexMgr.action == "create_index_loop":
        ftsIndexMgr.create_fts_indexes_in_a_loop(ftsIndexMgr.timeout, ftsIndexMgr.interval)
    elif ftsIndexMgr.action == "create_index_loop_on_bucket":
        ftsIndexMgr.create_fts_indexes_in_a_loop_on_bucket(ftsIndexMgr.timeout, ftsIndexMgr.interval)
    elif ftsIndexMgr.action == "item_count_check":
        ftsIndexMgr.item_count_check()
    elif ftsIndexMgr.action == "active_queries_check":
        ftsIndexMgr.active_queries_check()
    elif ftsIndexMgr.action == "run_flex_queries":
        ftsIndexMgr.run_flex_queries()
    elif ftsIndexMgr.action == "copy_docs_from_source_collection":
        ftsIndexMgr.copy_docs_source_collection()
    elif ftsIndexMgr.action == "update_docs_on_all_collections":
        ftsIndexMgr.update_docs()
    elif ftsIndexMgr.action == "run_knn_queries" or ftsIndexMgr.action == "run_knn_and_fts_queries":
        ftsIndexMgr.run_knn_queries()
    else:
        print(
            "Invalid choice for action. Choose from the following - create_index | build_deferred_index | drop_all_indexes")

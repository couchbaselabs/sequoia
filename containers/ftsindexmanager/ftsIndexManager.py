import base64
import copy
import json
import socket
import string
import sys
import threading
from concurrent.futures import as_completed
from concurrent.futures.thread import ThreadPoolExecutor
from datetime import datetime
from http.client import RemoteDisconnected

from couchbase.cluster import Cluster, ClusterOptions, QueryOptions
from couchbase.exceptions import QueryException, QueryIndexAlreadyExistsException, TimeoutException
from couchbase_core.cluster import PasswordAuthenticator
from couchbase_core.bucketmanager import BucketManager
from couchbase.management.collections import *
from couchbase.management.admin import *
from couchbase.search import QueryStringQuery, SearchQuery, SearchOptions, PrefixQuery, HighlightStyle, SortField, \
    SortScore, TermFacet
import random
import argparse
import logging
import requests
import time
import httplib2
import json

## Constants

HOTEL_DS_FIELDS = [
    {
        "name": "country",
        "type": "text",
        "is_nested_object": False,
        "field_code": "country",
        "queries": [{
            "match": "Moldova",
            "field": "country",
            "fuzziness": 2,
            "operator": "and"
        },
            {
                "match": "Cape Verde",
                "field": "country",
                "fuzziness": 2,
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
            }]},
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
            }]},
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
            }]},
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
            }]},
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
            }]},
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
            }]}
]

# Some constants
NUM_WORKERS = 2  # Max number of worker threads to execute queries
BATCH_SIZE = 20  # Number of FTS queries to be run by each worker thread
FTS_PORT = 8094


class FTSIndexManager:

    def __init__(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("-n", "--node", help="Couchbase Server Node Address")
        parser.add_argument("-o", "--port", help="Couchbase Server Node Port")
        parser.add_argument("-u", "--username", help="Couchbase Server Cluster Username")
        parser.add_argument("-p", "--password", help="Couchbase Server Cluster Password")
        parser.add_argument("-b", "--bucket", help="Bucket name on which indexes are to be created")
        parser.add_argument("-i", "--num_indexes", type=int,
                            help="Number of indexes to be created on collections for a bucket, if action = create_index. "
                                 "If action=drop_index, number of indexes to be dropped per collection of bucket")
        parser.add_argument("-d", "--dataset", help="Dataset to be used for the test. Choices are - hotel",
                            default="hotel")
        parser.add_argument("-t", "--duration", type=int,
                            help="Duration for queries to be run for. 0 (default) is infinite",
                            default="0")
        parser.add_argument("--print_interval", type=int,
                            help="Interval to print query result summary. Default is 10 mins",
                            default="600")
        parser.add_argument("--interval", type=int, default=60,
                            help="Interval between 2 create index calls when running in a loop")
        parser.add_argument("--timeout", type=int, default=0,
                            help="Timeout for create index loop. 0 (default) is infinite")
        parser.add_argument("-a", "--action",
                            choices=["create_index", "run_queries", "delete_all_indexes", "create_index_loop"],
                            help="Choose an action to be performed. Valid actions : create_index, run_queries, delete_all_indexes, create_index_loop",
                            default="create_index")

        args = parser.parse_args()

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
        self.timeout = args.timeout

        self.idx_def_templates = HOTEL_DS_FIELDS

        # If there are more datasets supported, this can be expanded.
        if self.dataset == "hotel":
            self.idx_def_templates = HOTEL_DS_FIELDS

        # Initialize connections to the cluster
        self.cb_admin = Admin(self.username, self.password, self.node_addr, self.node_port)
        self.cb_coll_mgr = CollectionManager(self.cb_admin, self.bucket_name)
        self.cluster = Cluster('couchbase://{0}'.format(self.node_addr),
                               ClusterOptions(PasswordAuthenticator(self.username, self.password)))
        self.cb = self.cluster.bucket(self.bucket_name)
        self.cluster.search_indexes()

        # Logging configuration

        self.log = logging.getLogger("ftsindexmanager")
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

    """
    Fetch list of all collections for the given bucket
    """

    def get_all_collections(self):
        cb_scopes = self.cb.collections().get_all_scopes()

        keyspace_name_list = []
        for scope in cb_scopes:
            for coll in scope.collections:
                keyspace_name_list.append(scope.name + "." + coll.name)
        return (keyspace_name_list)

    """
    Fetch list of all scopes that have multiple collections
    """

    def get_all_scopes_with_multiple_collections(self):
        cb_scopes = self.cb.collections().get_all_scopes()

        multi_coll_scopes = []

        for scope in cb_scopes:
            scope_obj = {}
            collections = []
            for coll in scope.collections:
                collections.append(scope.name + "." + coll.name)
            if len(collections) > 1:
                scope_obj[scope.name] = collections
                multi_coll_scopes.append(scope_obj)
        return multi_coll_scopes

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
            status, content, response = self.create_fts_index_on_collections(collections)

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
        while True:

            coll_list = self.get_all_collections()
            multi_coll_scopes = self.get_all_scopes_with_multiple_collections()

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
            status, content, response = self.create_fts_index_on_collections(collections)

            if not status:
                self.log.info("Content = {0} \nResponse = {1}".format(content, response))
                self.log.info("Index creation on {0} did not succeed. Pls check logs.".format(collections))

            # Exit if timed out
            if timeout > 0 and time.time() > end_time:
                break

        # Wait for the interval before doing the next CRUD operation
        time.sleep(interval)




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

    def create_fts_index_on_collections(self, collections):

        # Randomly select fields to create the index on
        ds_fields = copy.deepcopy(HOTEL_DS_FIELDS)
        if self.dataset == "hotel":
            ds_fields = copy.deepcopy(HOTEL_DS_FIELDS)

        num_fields = random.randint(1, len(ds_fields))
        index_fields = []
        for i in range(num_fields):
            field = random.choice(ds_fields)
            ds_fields.remove(field)
            index_fields.append(field)

        self.log.debug("***********  Fields selected for index : {0}".format(index_fields))

        # Randomly choose number of partitions and replicas
        num_partitions = random.randint(2, self.max_num_partitions)
        num_replica = random.randint(0, self.max_num_replica)

        # Generate index name. Index names will also have field codes so that the query runner can decode the fields used in the index.
        idx_name = "idx_" + ''.join(random.choice(string.ascii_lowercase) for i in range(5))
        for field in index_fields:
            idx_name += "-" + field["field_code"]

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
        index_def_dict["params"]["mapping"]["default_analyzer"] = "keyword"
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
        status, content, response = self.http_request(self.node_addr, FTS_PORT, "/api/index/{0}".format(idx_name),
                                                      method="PUT", body=index_definition)

        return status, content, response

    """
    Retrieve list of FTS indexes in the cluster
    """

    def get_fts_index_list(self):
        index_names = []
        status, content, response = self.http_request(self.node_addr, FTS_PORT, "/api/index")
        if status:
            index_names = list(content["indexDefs"]["indexDefs"].keys())
            # self.log.info("FTS indexes in cluster - \n : ".format(list(content["indexDefs"]["indexDefs"].keys())))
            self.log.debug("FTS indexes in cluster - : \n{0}".format(index_names))

        return index_names

    """
    Delete all FTS indexes
    """

    def delete_all_indexes(self):
        index_names = self.get_fts_index_list()
        for index in index_names:
            uri = "/api/index/" + index
            status, content, response = self.http_request(self.node_addr, FTS_PORT, uri, method="DELETE")
            if not status:
                self.log.info("Status : {0} \nResponse : {1} \nContent : {2}".format(status, response, content))
                self.log.info("Index {0} not deleted".format(index))

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
                for i in range(BATCH_SIZE):
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
                    self.log.info("======== Queries Run = {0} | Queries Passed = {1} | Queries Failed = {2} ========".format(queries_run, queries_passed, queries_failed))
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
    Run FTS queries on random index with random fields
    """

    def generate_and_run_fts_query(self):
        index_names = self.get_fts_index_list()

        index_name = random.choice(index_names)
        index_fields = self.get_index_fields(index_name)
        index_field = random.choice(index_fields)
        self.log.info("--------------- Running query on {0} field {1} ---------------".format(index_name, index_field))
        query = random.choice(index_field["queries"])

        if "score_none" in index_field:
            status, content, response = self.run_fts_query(index_name, query, score_none=True)
        else:
            status, content, response = self.run_fts_query(index_name, query, score_none=False)

        try:
            if status:
                self.log.info("Status : {0} \nResponse : {1} \nTotal Hits : {2}".format(status, response["status"],
                                                                                content["total_hits"]))
        except TypeError as terr:
            self.log.debug("terr")
            self.log.info("Content does not have total hits = {0}".format(content))
        except:
            self.log.error("Unexpected error :", sys.exc_info()[0])

        return status

    """
    Run single FTS query
    """

    def run_fts_query(self, index_name, query, score_none=False):
        uri = "/api/index/" + index_name + "/query"

        body = {}
        body["explain"] = True
        body["fields"] = ["*"]
        body["highlight"] = {}
        body["query"] = query
        body["explain"] = random.choice([True, False])
        if score_none:
            body["score"] = "none"

        # Randomize size (not more than 1000)
        size = random.randint(100, 1000)

        # Randomize offset (from)
        offset = random.randint(0, 10000)

        body["size"] = size
        body["from"] = offset

        self.log.info("URI : {0} body : {1}".format(uri, body))

        #Randomize FTS host on which the query has to be run for load distribution
        fts_node_list = self.find_nodes_with_service(self.get_services_map(), "fts")
        query_host = random.choice(fts_node_list)
        status, content, response = self.http_request(query_host, FTS_PORT, uri, method="POST", body=json.dumps(body))

        return status, content, response

    """
    Generic method to perform a REST call
    """
    def http_request(self, host, port, uri, method="GET", body=None):
        credentials = '{}:{}'.format(self.username, self.password)
        authorization = base64.encodebytes(credentials.encode('utf-8'))
        authorization = authorization.decode('utf-8').rstrip('\n')

        headers = {'Content-Type': 'application/json',
                   'Authorization': 'Basic %s' % authorization,
                   'Accept': '*/*'}

        url = "http://" + host + ":" + str(port) + uri
        http = httplib2.Http(timeout=120)
        http.add_credentials(self.username, self.password)
        try:
            response, content = http.request(uri=url, method=method, headers=headers, body=body)

        except (RemoteDisconnected, httplib2.HttpLib2Error, socket.error) as ex:
            self.log.info(ex)
            self.log.info("Request timed out")
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
        self.log.info("Setting Max Replica for this test to : {0}".format(self.max_num_replica))

    """
    Populate the service map for all nodes in the cluster.
    """

    def get_services_map(self):
        cluster_url = "http://" + self.node_addr + ":" + self.node_port + "/pools/default"
        node_map = []

        # Get map of nodes in the cluster
        response = requests.get(cluster_url, auth=(
            self.username, self.password), verify=True, )

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
    elif ftsIndexMgr.action == "run_queries":
        ftsIndexMgr.fts_query_runner()
    elif ftsIndexMgr.action == "delete_all_indexes":
        ftsIndexMgr.delete_all_indexes()
    elif ftsIndexMgr.action == "create_index_loop":
        ftsIndexMgr.create_fts_indexes_in_a_loop(ftsIndexMgr.timeout, ftsIndexMgr.interval)
    else:
        print(
            "Invalid choice for action. Choose from the following - create_index | build_deferred_index | drop_all_indexes")

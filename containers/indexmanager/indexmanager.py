import json
import sys
from datetime import datetime
from couchbase.cluster import Cluster, ClusterOptions, QueryOptions
from couchbase.exceptions import QueryException, QueryIndexAlreadyExistsException,TimeoutException
from couchbase_core.cluster import PasswordAuthenticator
from couchbase_core.bucketmanager import BucketManager
from couchbase.management.collections import *
from couchbase.management.admin import *
import random
import argparse
import logging
import requests
import time

## Constants

# In test mode, how many scopes to be created
TOTAL_SCOPES = 1

# In test mode, how many collections to be created per scope
TOTAL_COLL_PER_SCOPE = 2

# In test mode, SUFFIX for scope name - <bucket name>_scope
SCOPENAME_SUFFIX = "_scope"

##Templates for data-set specific index statements

# Hotel DS
HOTEL_DS_INDEX_TEMPLATES = [
    {"indexname": "idx1",
     "statement": "CREATE INDEX idx1 ON keyspacenameplaceholder(country, DISTINCT ARRAY `r`.`ratings`.`Check in / front desk` FOR r in `reviews` END,array_count((`public_likes`)),array_count((`reviews`)) DESC,`type`,`phone`,`price`,`email`,`address`,`name`,`url`) "},
    {"indexname": "idx2",
     "statement": "CREATE INDEX idx2 ON keyspacenameplaceholder(`free_breakfast`,`type`,`free_parking`,array_count((`public_likes`)),`price`,`country`)"},
    {"indexname": "idx3",
     "statement": "CREATE INDEX idx3 ON keyspacenameplaceholder(`free_breakfast`,`free_parking`,`country`,`city`) "}
]


class IndexManager:

    def __init__(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("-n", "--node", help="Couchbase Server Node Address")
        parser.add_argument("-o", "--port", help="Couchbase Server Node Port")
        parser.add_argument("-u", "--username", help="Couchbase Server Cluster Username")
        parser.add_argument("-p", "--password", help="Couchbase Server Cluster Password")
        parser.add_argument("-b", "--bucket", help="Bucket name on which indexes are to be created")
        parser.add_argument("-i", "--num_index_per_collection", type=int,
                            help="Number of indexes to be created per collection of bucket, if action = create_index. "
                                 "If action=drop_index, number of indexes to be dropped per collection of bucket")
        parser.add_argument("-d", "--dataset", help="Dataset to be used for the test. Choices are - hotel",
                            default="hotel")
        parser.add_argument("-a", "--action", choices=["create_index", "build_deferred_index", "drop_all_indexes"],
                            help="Choose an action to be performed. Valid actions : create_index | build_deferred_index"
                                 " | drop_all_indexes", default="create_index")
        parser.add_argument("-m", "--build_max_collections", type=int, default=0, help="Build Indexes on max number of collections")
        parser.add_argument("-t", "--test_mode", help="Test Mode : Create Scopes/Collections", action='store_true')
        args = parser.parse_args()

        self.node_addr = args.node
        self.node_port = args.port
        self.username = args.username
        self.password = args.password
        self.bucket_name = args.bucket
        self.num_index_per_coll = args.num_index_per_collection
        self.dataset = args.dataset
        self.action = args.action
        self.test_mode = args.test_mode
        self.max_num_collections = args.build_max_collections

        self.idx_def_templates = HOTEL_DS_INDEX_TEMPLATES

        # If there are more datasets supported, this can be expanded.
        if self.dataset == "hotel":
            self.idx_def_templates = HOTEL_DS_INDEX_TEMPLATES

        # Initialize connections to the cluster
        self.cb_admin = Admin(self.username, self.password, self.node_addr, self.node_port)
        self.cb_coll_mgr = CollectionManager(self.cb_admin, self.bucket_name)
        self.cluster = Cluster('couchbase://{0}'.format(self.node_addr),
                               ClusterOptions(PasswordAuthenticator(self.username, self.password)))
        self.cb = self.cluster.bucket(self.bucket_name)

        # Logging configuration

        self.log = logging.getLogger("indexmanager")
        self.log.setLevel(logging.INFO)
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        ch.setFormatter(formatter)
        self.log.addHandler(ch)
        timestamp = str(datetime.now().strftime('%Y%m%dT_%H%M%S'))
        fh = logging.FileHandler("./indexmanager-{0}.log".format(timestamp))
        fh.setFormatter(formatter)
        self.log.addHandler(fh)

        # Set max number of replica for the test. For that, fetch the number of indexer nodes in the cluster.
        self.max_num_replica = 0
        self.max_num_partitions = 4
        self.set_max_num_replica()

    """
    Create scope and collections in the cluster for the given bucket when the test mode is on.
    """

    def create_scopes_collections(self):
        for i in range(0, TOTAL_SCOPES):
            scopename = self.bucket_name + SCOPENAME_SUFFIX + str(i + 1)
            self.cb_coll_mgr.create_scope(scopename)

            for j in range(0, TOTAL_COLL_PER_SCOPE):
                collectionname = scopename + "_coll" + str(j + 1)
                coll_spec = CollectionSpec(collectionname, scopename)
                self.cb_coll_mgr.create_collection(coll_spec)

    """
    Fetch list of all collections for the given bucket
    """

    def get_all_collections(self):
        cb_scopes = self.cb.collections().get_all_scopes()

        keyspace_name_list = []
        for scope in cb_scopes:
            for coll in scope.collections:
                keyspace_name_list.append("`" + self.bucket_name + "`.`" + scope.name + "`.`" + coll.name + "`")

        return (keyspace_name_list)

    """
    Create indexes on the given bucket.
    1. Determine number of indexes to be created
    2. Select index definition template based on the dataset
    3. For each collection, select a index definition template
    4. Randomize if the index needs to have replicas, partitions or defer_build
    5. Based on the above final definition, calculate number of index instances.
    6. Loop from Step 3 to 6 until total number of index instances are totalling  
       to the number of indexes to be created as determined in Step 1.
    7. Create the indexes serially.
    """

    def create_indexes_on_bucket(self, keyspace_name_list):
        # max_num_idx = TOTAL_SCOPES * TOTAL_COLL_PER_SCOPE * self.num_index_per_coll
        max_num_idx = len(keyspace_name_list) * self.num_index_per_coll
        total_idx_created = 0
        create_index_statements = []
        self.log.info("Starting to create indexes ")
        while total_idx_created < max_num_idx:
            keyspaceused = []
            for keyspacename in keyspace_name_list:
                keyspaceused.append(keyspacename)
                for idx_template in self.idx_def_templates:
                    idx_statement = idx_template['statement']
                    is_partitioned_idx = bool(random.getrandbits(1))
                    is_defer_idx = bool(random.getrandbits(1))
                    idx_instances = 1
                    with_clause_list = []

                    if is_partitioned_idx:
                        idx_statement = idx_statement + " partition by hash(meta().id) "
                        num_partition = random.randint(2, self.max_num_partitions + 1)
                        with_clause_list.append("\'num_partition\':%s" % num_partition)
                        idx_instances *= num_partition

                    if self.max_num_replica > 0:
                        num_replica = random.randint(1, self.max_num_replica)
                        with_clause_list.append("\'num_replica\':%s" % num_replica)
                        idx_instances *= num_replica + 1

                    if is_defer_idx:
                        with_clause_list.append("\'defer_build\':true")

                    if is_partitioned_idx or (self.max_num_replica > 0) or is_defer_idx:
                        idx_statement = idx_statement + " with {"
                        idx_statement = idx_statement + ','.join(with_clause_list) + "}"

                    idx_statement = idx_statement.replace("keyspacenameplaceholder", keyspacename)

                    create_index_statements.append(idx_statement)

                    total_idx_created += idx_instances
                    if total_idx_created >= max_num_idx:
                        break
                if total_idx_created >= max_num_idx:
                    break

        self.log.info("**************************************************")
        self.log.info("Total Indexes : %s" % total_idx_created)
        self.log.debug("Keyspaces used : ")
        self.log.debug(keyspaceused)

        for create_index_statement in create_index_statements:
            self.log.info("Creating index : %s" % create_index_statement)

            status, results, queryResult = self._execute_query(create_index_statement)
        self.log.info("Create indexes completed")

    """
    Determine number of index nodes in the cluster and set max num replica accordingly.
    """

    def set_max_num_replica(self):
        nodelist = self.find_nodes_with_service(self.get_services_map(), "index")
        self.max_num_replica = len(nodelist) - 1  # Max num replica = number of idx nodes in cluster - 1
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
                mem_used = int(node["memoryTotal"]) - int(node["memoryFree"])
                clusternode["memUsage"] = round(
                    float(mem_used / float(node["memoryTotal"]) * 100), 2)
                clusternode["cpuUsage"] = round(
                    node["systemStats"]["cpu_utilization_rate"], 2)
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

    # Not working with collections in Python SDK 3.0.4. To be revisited when implemented

    # def build_all_deferred_indexes_sdk(self, keyspace_name_list):
    #    mgr = BucketManager(self.cb, self.bucket_name)
    #    mgr.build_n1ql_deferred_indexes()

    """
    Build all deferred indexes for all collections of the specified bucket. For each collection, issue a build index 
    query with a subquery that would fetch all deferred indexes for that collection.
    """

    def build_all_deferred_indexes(self, keyspace_name_list, max_collections_to_build=0):
        build_index_query_template = "build index on keyspacename (( select raw name from system:all_indexes where " \
                                     "`using`='gsi' and '`' || `bucket_id` || '`.`' || `scope_id` || '`.`' || " \
                                     "`keyspace_id` || '`' = 'keyspacename' and state = 'deferred'))"
        counter = 0
        keyspace_batch = []
        for keyspace in keyspace_name_list:
            if max_collections_to_build > 0:
                if counter < 10:
                    build_index_query = build_index_query_template.replace("keyspacename", keyspace)
                    self.log.info("Building indexes for keyspace : {0}".format(keyspace))
                    self.log.debug("Query used = {0}".format(build_index_query))

                    status, results, queryResult = self._execute_query(build_index_query)
                    counter += 1
                    keyspace_batch.append(keyspace)

                    # Sleep for 2 secs after issuing a build index for all indexes for a collection
                    sleep(2)
                else:
                    # Wait for all indexes to be built
                    indexes_built = self.wait_for_indexes_to_be_built(keyspace_batch)
                    if not indexes_built:
                        self.log.error("All indexes not built until timed out")
                        break
                    counter = 0
                    keyspace_batch.clear()
            else:
                build_index_query = build_index_query_template.replace("keyspacename", keyspace)
                self.log.info("Building indexes for keyspace : {0}".format(keyspace))
                self.log.debug("Query used = {0}".format(build_index_query))

                status, results, queryResult = self._execute_query(build_index_query)

                # Sleep for 2 secs after issuing a build index for all indexes for a collection
                sleep(2)

        if indexes_built:
            self.log.info("Building all deferred indexes completed ")

    """
    Drop all indexes in the cluster
    """

    def drop_all_indexes(self, keyspace_name_list):
        drop_idx_query_gen_template = "SELECT RAW 'DROP INDEX `' || name || '` on keyspacename;'  " \
                                      "FROM system:all_indexes WHERE '`' || `bucket_id` || '`.`' || `scope_id` " \
                                      "|| '`.`' || `keyspace_id` || '`' = 'keyspacename';"

        self.log.info("Starting to drop all indexes ")
        for keyspace in keyspace_name_list:
            drop_idx_query_gen = drop_idx_query_gen_template.replace("keyspacename", keyspace)

            status, results, queryResult = self._execute_query(drop_idx_query_gen)
            if status is not None:
                for result in results:
                    drop_status, _, _ = self._execute_query(result)

                    # Sleep for 2 secs after dropping an index
                    sleep(2)
        self.log.info("Drop all indexes completed")

    def wait_for_indexes_to_be_built(self, keyspace_name_list, timeout=3600, sleep_interval=15):

        # select count(*) from system_indexes where '`' || `bucket_id` || '`.`' || `scope_id` " \
        #                                       "|| '`.`' || `keyspace_id` || '`' in [keyspacename] and state!="online"
        index_status_check_query_template = "SELECT RAW count(*)  FROM system:all_indexes WHERE '`' || " \
                                            "`bucket_id` || '`.`' || `scope_id` || '`.`' || `keyspace_id` || '`' " \
                                            "in keyspace_name_list and state != 'online';"

        st_time = time.time()
        timedout = st_time + timeout
        indexes_online = False

        while (timedout > time.time()):
            query = index_status_check_query_template.replace("keyspace_name_list",str(keyspace_name_list))
            self.log.debug("Wait query : {0}".format(query))
            status, result, queryResult = self._execute_query(query)
            self.log.debug("Result = {0}".format(str(result)))
            if result == 0:
                indexes_online = True
                break
            else:
                self.log.debug("Waiting for indexes to be built")
                sleep(sleep_interval)

        if not indexes_online:
            self.log.warning("Timed out waiting for indexes to be online")

        return indexes_online




    """
    Method to execute a query statement 
    """

    def _execute_query(self, statement):
        status = None
        results = None
        queryResult = None

        try:
            timeout = timedelta(minutes=5)
            queryResult = self.cluster.query(statement,QueryOptions(timeout=timeout))
            status = queryResult.metadata().status()
            results = queryResult.rows()

        except QueryException as qerr:
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
Main method
TODO : 1. Validation to check if indexes are created successfully
       2. Build all deferred indexes mode
       3. Wait for all indexes to be built mode
       4. Drop some indexes mode
"""
if __name__ == '__main__':
    indexMgr = IndexManager()
    if indexMgr.test_mode:
        indexMgr.create_scopes_collections()

    sleep(10)

    # Get list of all collections for the bucket
    keyspace_name_list = indexMgr.get_all_collections()

    if indexMgr.action == "create_index":
        indexMgr.create_indexes_on_bucket(keyspace_name_list)
    elif indexMgr.action == "build_deferred_index":
        indexMgr.build_all_deferred_indexes(keyspace_name_list, indexMgr.max_num_collections)
        # The SDK way to build all deferred indexes is not yet working in Python SDK 3.0.4. To revisit once implemented.
        # indexMgr.build_all_deferred_indexes_sdk(keyspace_name_list)
    elif indexMgr.action == "drop_all_indexes":
        indexMgr.drop_all_indexes(keyspace_name_list)
    else:
        print(
            "Invalid choice for action. Choose from the following - create_index | build_deferred_index | drop_all_indexes")

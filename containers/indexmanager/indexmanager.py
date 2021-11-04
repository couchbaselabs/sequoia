import json
import string
import sys
from datetime import datetime
from couchbase.cluster import Cluster, ClusterOptions, QueryOptions
import couchbase.exceptions
from couchbase_core.cluster import PasswordAuthenticator
from couchbase_core.bucketmanager import BucketManager
from couchbase.management.collections import *
from couchbase.management.admin import *
import random
import argparse
import logging
import requests
import time
import math
import httplib2
import paramiko

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
     "statement": "CREATE INDEX `idx1_idxprefix` ON keyspacenameplaceholder(country, DISTINCT ARRAY `r`.`ratings`.`Check in / front desk` FOR r in `reviews` END,array_count((`public_likes`)),array_count((`reviews`)) DESC,`type`,`phone`,`price`,`email`,`address`,`name`,`url`) "},
    {"indexname": "idx2",
     "statement": "CREATE INDEX `idx2_idxprefix` ON keyspacenameplaceholder(`free_breakfast`,`type`,`free_parking`,array_count((`public_likes`)),`price`,`country`)"},
    {"indexname": "idx3",
     "statement": "CREATE INDEX `idx3_idxprefix` ON keyspacenameplaceholder(`free_breakfast`,`free_parking`,`country`,`city`) "},
    {"indexname": "idx4",
     "statement": "CREATE INDEX `idx4_idxprefix` ON keyspacenameplaceholder(`price`,`city`,`name`)"},
    {"indexname": "idx5",
     "statement": "CREATE INDEX `idx5_idxprefix` ON keyspacenameplaceholder(ALL ARRAY `r`.`ratings`.`Rooms` FOR r IN `reviews` END,`avg_rating`)"},
    {"indexname": "idx6",
     "statement": "CREATE INDEX `idx6_idxprefix` ON keyspacenameplaceholder(`city`)"},
    {"indexname": "idx7",
     "statement": "CREATE INDEX `idx7_idxprefix` ON keyspacenameplaceholder(`price`,`name`,`city`,`country`)"},
    {"indexname": "idx8",
     "statement": "CREATE INDEX `idx8_idxprefix` ON keyspacenameplaceholder(DISTINCT ARRAY FLATTEN_KEYS(`r`.`author`,`r`.`ratings`.`Cleanliness`) FOR r IN `reviews` when `r`.`ratings`.`Cleanliness` < 4 END, `country`, `email`, `free_parking`)"},
    {"indexname": "idx9",
     "statement": "CREATE INDEX `idx9_idxprefix` ON keyspacenameplaceholder(ALL ARRAY FLATTEN_KEYS(`r`.`author`,`r`.`ratings`.`Rooms`) FOR r IN `reviews` END, `free_parking`)"},
    {"indexname": "idx10",
     "statement": "CREATE INDEX `idx10_idxprefix` ON keyspacenameplaceholder((ALL (ARRAY(ALL (ARRAY flatten_keys(n,v) FOR n:v IN (`r`.`ratings`) END)) FOR `r` IN `reviews` END)))"},
    {"indexname": "idx11",
     "statement": "CREATE INDEX `idx11_idxprefix` ON keyspacenameplaceholder(ALL ARRAY FLATTEN_KEYS(`r`.`ratings`.`Rooms`,`r`.`ratings`.`Cleanliness`) FOR r IN `reviews` END, `email`, `free_parking`)"}
]

HOTEL_DS_CBO_FIELDS = "`country`, DISTINCT ARRAY `r`.`ratings`.`Check in / front desk`, array_count((`public_likes`)),array_count((`reviews`)) DESC,`type`,`phone`,`price`,`email`,`address`,`name`,`url`,`free_breakfast`,`free_parking`,`city`"


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
        parser.add_argument("-a", "--action",
                            choices=["create_index", "build_deferred_index", "drop_all_indexes", "create_index_loop",
                                     "drop_index_loop", "alter_indexes", "enable_cbo", "delete_statistics",
                                     "item_count_check",
                                     "random_recovery", "create_udf", "drop_udf"],
                            help="Choose an action to be performed. Valid actions : create_index | build_deferred_index | drop_all_indexes | create_index_loop | "
                                 "drop_index_loop | alter_indexes | enable_cbo | delete_statistics | item_count_check | random_recovery | create_udf | drop_udf",
                            default="create_index")
        parser.add_argument("-m", "--build_max_collections", type=int, default=0,
                            help="Build Indexes on max number of collections")
        parser.add_argument("--interval", type=int, default=60,
                            help="Interval between 2 create index statements when running in a loop")
        parser.add_argument("--timeout", type=int, default=0,
                            help="Timeout for create index loop. 0 (default) is infinite")
        parser.add_argument("--cbo_enable_ratio", type=int, default=25,
                            help="Specify on how many % of collections should CBO be enabled. Range = 1-100")
        parser.add_argument("--cbo_interval", type=int, default=15,
                            help="Interval (minutes) to update statistics on collections of a bucket")
        parser.add_argument("--sample_size", type=int, default=5,
                            help="Specify how many indexes to be sampled for item count check. Default = 5")
        parser.add_argument("--num_udf_per_scope", type=int, default=10,
                            help="Specify how many UDF to be created per scope. Default = 10")
        parser.add_argument("-v", "--validate", help="Validation required for create_index and drop_all_indexes action",
                            action='store_true')
        parser.add_argument("-t", "--test_mode", help="Test Mode : Create Scopes/Collections", action='store_true')
        parser.add_argument("-im", "--install_mode", help="install mode: ce or ee", default="ee")
        parser.add_argument("--no_partitioned_indexes", help="No partitioned indexes to be created",
                            action="store_true")
        args = parser.parse_args()

        self.node_addr = args.node
        self.node_port = args.port
        self.username = args.username
        self.password = args.password
        self.bucket_name = args.bucket
        self.num_index_per_coll = args.num_index_per_collection
        self.dataset = args.dataset
        self.action = args.action
        self.interval = args.interval
        self.timeout = args.timeout
        self.test_mode = args.test_mode
        self.validate = args.validate
        self.install_mode = args.install_mode
        self.max_num_collections = args.build_max_collections
        self.cbo_enable_ratio = args.cbo_enable_ratio
        if self.cbo_enable_ratio > 100:
            self.cbo_enable_ratio = 25
        self.cbo_interval = args.cbo_interval
        self.sample_size = args.sample_size
        self.num_udf_per_scope = args.num_udf_per_scope
        self.disable_partitioned_indexes = args.no_partitioned_indexes

        self.idx_def_templates = HOTEL_DS_INDEX_TEMPLATES
        # If there are more datasets supported, this can be expanded.
        if self.dataset == "hotel":
            self.idx_def_templates = HOTEL_DS_INDEX_TEMPLATES
            self.cbo_fields = HOTEL_DS_CBO_FIELDS

        # Initialize connections to the cluster
        self.cb_admin = Admin(self.username, self.password, self.node_addr, self.node_port)
        self.cb_coll_mgr = CollectionManager(self.cb_admin, self.bucket_name)
        self.cluster = Cluster('couchbase://{0}'.format(self.node_addr),
                               ClusterOptions(PasswordAuthenticator(self.username, self.password)))
        self.cb = self.cluster.bucket(self.bucket_name)
        self.index_nodes = self.find_nodes_with_service(self.get_services_map(), "index")

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

        # Node SSH default credentials
        self.ssh_username = "root"
        self.ssh_password = "couchbase"

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
        self.log.info(str(keyspace_name_list))

        # Shuffle the list twice so that the indexes on collections can be more spread out.
        random.shuffle(keyspace_name_list)
        random.shuffle(keyspace_name_list)

        return (keyspace_name_list)

    def create_indexes_on_bucket_in_a_loop(self, timeout, interval):
        # Establish timeout. If timeout > 0, run in infinite loop
        end_time = 0
        if timeout > 0:
            end_time = time.time() + timeout
        while True:
            random.seed(datetime.now())

            keyspace_name_list = self.get_all_collections()
            keyspace_name = random.choice(keyspace_name_list)
            idx_template = random.choice(self.idx_def_templates)
            idx_statement = idx_template['statement']
            idx_name = idx_template['indexname']

            is_partitioned_idx = bool(random.getrandbits(1))
            is_defer_idx = bool(random.getrandbits(1))
            idx_instances = 1
            with_clause_list = []

            if is_partitioned_idx and (not self.disable_partitioned_indexes):
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

            idx_statement = idx_statement.replace("keyspacenameplaceholder", keyspace_name)
            new_idx_name = idx_name + "_" + ''.join(random.choices(string.ascii_uppercase +
                                                                   string.digits, k=10))
            idx_statement = idx_statement.replace(idx_name, new_idx_name)

            self.log.info("Creating index : %s" % idx_statement)

            status, results, queryResult = self._execute_query(idx_statement)
            if status is None:
                # raise Exception("Query service probably has issues")
                self.log.info("Some issue running the create index statement")

            # Exit if timed out
            if timeout > 0 and time.time() > end_time:
                break

            # Wait for the interval before doing the next CRUD operation
            sleep(interval)

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

    def create_indexes_on_bucket(self, keyspace_name_list, validate=True):
        # max_num_idx = TOTAL_SCOPES * TOTAL_COLL_PER_SCOPE * self.num_index_per_coll
        max_num_idx = len(keyspace_name_list) * self.num_index_per_coll
        total_idx_created = 0
        total_idx = 0
        create_index_statements = []
        self.log.info("Starting to create indexes ")
        reference_index_map = NestedDict()
        keyspaceused = []
        while total_idx_created < max_num_idx:
            for keyspace_name in keyspace_name_list:
                bucket, scope, collection = keyspace_name.split('.')
                keyspaceused.append(keyspace_name)

                # Choose upto 3 random template definitions to create indexes with
                idx_def_templates = random.sample(self.idx_def_templates, 3)
                for idx_template in idx_def_templates:
                    idx_statement = idx_template['statement']

                    idx_prefix = ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(4, 8)))
                    idx_name = f"{idx_template['indexname']}_{idx_prefix}"

                    is_partitioned_idx = bool(random.getrandbits(1))
                    is_defer_idx = bool(random.getrandbits(1))
                    idx_instances = 1
                    num_idx = 1
                    with_clause_list = []
                    idx_statement = idx_statement.replace("keyspacenameplaceholder", keyspace_name)
                    idx_statement = idx_statement.replace('idxprefix', idx_prefix)

                    keyspace_name = keyspace_name.replace('`', '')
                    reference_index_map[keyspace_name][idx_name]['bucket'] = bucket
                    reference_index_map[keyspace_name][idx_name]['scope'] = scope
                    reference_index_map[keyspace_name][idx_name]['collection'] = collection
                    reference_index_map[keyspace_name][idx_name]['defer'] = is_defer_idx
                    reference_index_map[keyspace_name][idx_name]['partition'] = is_partitioned_idx

                    if self.install_mode == "ee" and is_partitioned_idx and (not self.disable_partitioned_indexes):
                        idx_statement = idx_statement + " partition by hash(meta().id) "
                        num_partition = random.randint(2, self.max_num_partitions + 1)
                        with_clause_list.append("\'num_partition\':%s" % num_partition)
                        idx_instances *= num_partition
                        reference_index_map[keyspace_name][idx_name]['num_partition'] = num_partition
                    else:
                        reference_index_map[keyspace_name][idx_name]['num_partition'] = 1

                    if self.install_mode == "ee" and self.max_num_replica > 0:
                        num_replica = random.randint(1, self.max_num_replica)
                        with_clause_list.append("\'num_replica\':%s" % num_replica)
                        idx_instances *= num_replica + 1
                        reference_index_map[keyspace_name][idx_name]['replica_count'] = num_replica + 1

                    if is_defer_idx:
                        with_clause_list.append("\'defer_build\':true")

                    if (is_partitioned_idx and not self.disable_partitioned_indexes) or (
                            self.max_num_replica > 0) or is_defer_idx:
                        idx_statement = idx_statement + " with {"
                        idx_statement = idx_statement + ','.join(with_clause_list) + "}"

                    create_index_statements.append(idx_statement)
                    total_idx_created += idx_instances
                    total_idx += num_idx
                    if total_idx_created >= max_num_idx:
                        break
                if total_idx_created >= max_num_idx:
                    break

        self.log.info("**************************************************")
        self.log.info("Total Index instances : {0}, Total Indexes : {1}".format(total_idx_created, total_idx))

        self.log.debug("Keyspaces used : ")
        self.log.debug(keyspaceused)

        for create_index_statement in create_index_statements:
            self.log.info("Creating index : %s" % create_index_statement)
            try:
                self._execute_query(create_index_statement)
                sleep(10)
            except Exception as err:
                self.log.error(f"Index creation failed for statement: {create_index_statement}")
                self.log.error(err)
        self.log.info("Create indexes completed")
        if validate:
            self.wait_until_indexes_online(defer_build=False)
            index_map_from_system_indexes = self.get_index_map_from_system_indexes()
            for keyspace_name in reference_index_map.keys():
                ref_keyspace_dict = reference_index_map[keyspace_name]
                actual_keyspace_dict = index_map_from_system_indexes[keyspace_name]

                if sorted(ref_keyspace_dict.keys()) != sorted(actual_keyspace_dict.keys()):
                    self.log.error(f"Indexes are not matching with expected value.")
                    self.log.error(f" Expected: {ref_keyspace_dict}, Actual: {actual_keyspace_dict}")
                for index in ref_keyspace_dict.keys():
                    if ref_keyspace_dict[index]['defer']:
                        if actual_keyspace_dict[index]['state'] != 'deferred':
                            self.log.error(f"Index state is not matching with expected value."
                                           f" Expected 'deferred', Actual {actual_keyspace_dict[index]['state']} ")
                    else:
                        if actual_keyspace_dict[index]['state'] != 'online':
                            self.log.error(f"Index state is not matching with expected value."
                                           f" Expected 'online', Actual {actual_keyspace_dict[index]['state']} ")
                    if ref_keyspace_dict[index]['partition'] != actual_keyspace_dict[index]['partition']:
                        self.log.error(f"Index state is not matching with expected value."
                                       f"Expected: {ref_keyspace_dict}, Actual: {actual_keyspace_dict}")
            index_metadata = self.get_indexer_metadata()
            if 'status' not in index_metadata:
                self.log.error("Index metadata not correct : {0}".format(index_metadata))
                return
            index_status = index_metadata['status']
            for index in index_status:
                keyspace_name = f'{index["bucket"]}.{index["scope"]}.{index["collection"]}'
                index_name = index['indexName']
                if reference_index_map[keyspace_name][index_name]['replica_count'] != index['numReplica'] + 1:
                    self.log.error(f"Replica count is not matching with expected value."
                                   f"Expected: {index['numReplica'] + 1},"
                                   f" Actual: {reference_index_map[keyspace_name][index_name]['replica_count']}")
                if reference_index_map[keyspace_name][index_name]['num_partition'] != index['numPartition']:
                    self.log.error(f"Index Partition no. is not matching with expected value"
                                   f"Expected: {index['numPartition']},"
                                   f" Actual: {reference_index_map[keyspace_name][index_name]['numPartition']}")
                if reference_index_map[keyspace_name][index_name]['defer']:
                    if index['status'] != 'Created':
                        self.log.error(f"Index status is not matching with expected value"
                                       f"Expected: Created, Actual: {index['status']}")
                else:
                    if index['status'] != 'Ready':
                        self.log.error(f"Index status is not matching with expected value"
                                       f"Expected: Created, Actual: {index['status']}")
            self.log.info("Validation completed")

    """
    Alter indexes
    """

    def alter_indexes(self, timeout, interval=900):

        # Establish timeout. If timeout > 0, run in infinite loop
        end_time = 0
        if timeout > 0:
            end_time = time.time() + timeout
        while True:
            random.seed(datetime.now())

            # Get all index nodes in the cluster
            idx_node_list = self.find_nodes_with_service(self.get_services_map(), "index")
            idx_node_list.sort()

            # Get Index Map for indexes in the bucket
            index_map = self.get_index_map(self.bucket_name, idx_node_list[0])

            # Randomly choose an index to be altered
            index = random.choice(index_map)

            # Check the index for replicas
            idx_replica_count = index["numReplica"]

            # Check the index for hosts
            idx_hosts = []
            if idx_replica_count > 0:
                for idx in index_map:
                    if idx["defnId"] == index["defnId"]:
                        idx_hosts.extend(idx["hosts"])
            else:
                idx_hosts = index["hosts"]

            idx_unique_hosts = []
            [idx_unique_hosts.append(x) for x in idx_hosts if x not in idx_unique_hosts]
            idx_unique_hosts.sort()

            self.log.info(
                "Index selected to alter : {0} numReplica={1} numPartition={2} hosts={3}".format(index["indexName"],
                                                                                                 idx_replica_count,
                                                                                                 index["numPartition"],
                                                                                                 idx_unique_hosts))

            # Randomize action for alter index
            possible_actions = []
            if idx_replica_count > 0:
                if idx_replica_count == self.max_num_replica:
                    possible_actions = ["move", "decrease_replica_count", "drop_replica"]
                else:
                    possible_actions = ["move", "increase_replica_count", "decrease_replica_count", "drop_replica"]
            else:
                possible_actions = ["move", "increase_replica_count"]

            if len(idx_unique_hosts) < len(idx_node_list):
                possible_actions.append("move")

            alter_index_action = random.choice(possible_actions)

            # Perform action
            # Create and execute alter index query
            full_keyspace_name = "`" + index["bucket"] + "`.`" + index["scope"] + "`.`" + index["collection"] + "`"
            full_index_name = "default:" + full_keyspace_name + "." + index["indexName"]

            with_clause = {}
            if alter_index_action == "move":
                with_clause["action"] = "move"
                with_clause["nodes"] = []
                final_node_list = random.sample(idx_node_list, len(idx_unique_hosts))
                final_node_list.sort()
                if final_node_list == idx_unique_hosts:
                    final_node_list = random.sample(idx_node_list, len(idx_unique_hosts))
                    final_node_list.sort()

                for node in final_node_list:
                    with_clause["nodes"].append(node + ":8091")

            if alter_index_action == "increase_replica_count":
                with_clause["action"] = "replica_count"
                with_clause["num_replica"] = idx_replica_count + 1

            if alter_index_action == "decrease_replica_count":
                with_clause["action"] = "replica_count"
                with_clause["num_replica"] = idx_replica_count - 1

            if alter_index_action == "drop_replica":
                with_clause["action"] = "drop_replica"
                with_clause["replicaId"] = random.randint(0, idx_replica_count)

            alter_index_stmt = "ALTER INDEX " + full_index_name + " WITH " + str(with_clause)
            self.log.info("Alter index query : {0}".format(alter_index_stmt))

            status, results, queryResult = self._execute_query(alter_index_stmt)

            # Wait for indexes to be built completely
            self.wait_for_indexes_to_be_built([full_keyspace_name])

            # Exit if timed out
            if timeout > 0 and time.time() > end_time:
                break

            # Sleep for interval
            sleep(interval)

    def random_recovery(self, timeout=3600, min_frequency=120, max_frequency=900):
        # Establish timeout. If timeout = 0, run in infinite loop
        end_time = 0
        if timeout > 0:
            end_time = time.time() + timeout
        while True:

            # Get list of index nodes
            index_nodes = self.find_nodes_with_service(self.get_services_map(), "index")
            # Randomly choose one index node
            index_node_for_recovery = random.choice(index_nodes)
            # Kill indexer process on this node
            try:
                self.log.info("Killing indexer process on {0}".format(index_node_for_recovery))
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(index_node_for_recovery, username=self.ssh_username, password=self.ssh_password, timeout=10)
                ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("pkill -f indexer")
                out = ssh_stdout.read()
                err = ssh_stderr.read()
                self.log.error(
                    "Unable to kill indexer process on {0}. Error: {1}".format(index_node_for_recovery, str(err)))
            except Exception as e:
                self.log.error(str(e))
            finally:
                ssh.close()

            # Exit if timed out
            if timeout > 0 and time.time() > end_time:
                break
            # Sleep for random duration before the next recovery
            interval = random.randint(min_frequency, max_frequency)
            self.log.info("Sleeping for %s seconds" % str(interval))
            sleep(interval)

    def get_index_map_from_system_indexes(self):
        query = "Select * from system:indexes"
        status, result, _ = self._execute_query(query)
        index_map = NestedDict()
        for item in result:
            index = item['indexes']
            if 'scope_id' not in index:
                collection = '_default'
                scope = '_default'
                bucket = index['keyspace_id']
            else:
                bucket = index['bucket_id']
                scope = index['scope_id']
                collection = index['keyspace_id']
            state = index['state']
            index_key = index['index_key']
            index_name = index['name']
            keyspace = f"{bucket}.{scope}.{collection}"
            if 'is_primary' in index:
                index_map[keyspace][index_name]['is_primary'] = True
            else:
                index_map[keyspace][index_name]['is_primary'] = False
            if 'partition' in index:
                index_map[keyspace][index_name]['partition'] = True
                index_map[keyspace][index_name]['partition_key'] = index['partition']
            else:
                index_map[keyspace][index_name]['partition'] = False
                index_map[keyspace][index_name]['partition_key'] = None
            index_map[keyspace][index_name]['state'] = state
            index_map[keyspace][index_name]['index_key'] = index_key
        return index_map

    """
    Enable CBO on some collections randomly
    """

    def enable_cbo_and_update_statistics(self, cbo_collections_ratio=25):
        # Get list of all collections with indexes
        get_all_indexes_collections_query_for_bucket = "select distinct raw '`' || `bucket_id` || '`.`' || `scope_id` || '`.`' || `keyspace_id` || '`' from system:all_indexes where `using`='gsi' and `bucket_id` = '{0}'".format(
            self.bucket_name)
        try:
            status, results, queryResult = self._execute_query(get_all_indexes_collections_query_for_bucket)
        except Exception as e:
            self.log.error(str(e))

        keyspace_list = results

        # Select a few collections
        cbo_collections_list = random.sample(keyspace_list,
                                             math.floor(len(keyspace_list) * cbo_collections_ratio / 100))

        while True:
            # Run update statistics for these collections
            for coll in cbo_collections_list:
                try:
                    self.log.info("Running Update Statistics for {0}".format(coll))
                    update_stats_query = "UPDATE STATISTICS FOR {0} INDEX ALL WITH {{'update_statistics_timeout': 0}}  ;".format(coll)
                    status, results, queryResult = self._execute_query(update_stats_query)
                    sleep(2)
                except Exception as e:
                    self.log.error(str(e))

            # Periodically update statistics in a loop for these collections
            self.log.info("*** Sleeping for {0} mins until the next iteration for update statistics ***".format(
                self.cbo_interval))
            sleep(self.cbo_interval * 60)

    """
    Delete Statistics on all collections
    """

    def delete_statistics(self):
        # Get list of all collections with indexes
        get_all_indexes_collections_query_for_bucket = "select distinct raw '`' || `bucket_id` || '`.`' || `scope_id` || '`.`' || `keyspace_id` || '`' from system:all_indexes where `using`='gsi' and `bucket_id` = '{0}'".format(
            self.bucket_name)
        try:
            status, results, queryResult = self._execute_query(get_all_indexes_collections_query_for_bucket)
        except Exception as e:
            self.log.error(str(e))

        keyspace_list = results
        for coll in keyspace_list:
            try:
                self.log.info("Running Delete Statistics for {0}".format(coll))
                update_stats_query = "UPDATE STATISTICS FOR {0} DELETE ALL;".format(coll)
                status, results, queryResult = self._execute_query(update_stats_query)
                sleep(2)
            except Exception as e:
                self.log.error(str(e))

    """
    Item Count Check
    1. Get the index map for a given bucket
    2. Randomly select some indexes from the index map 
    3. For each selected index, extract items_count for index stat from the stats endpoint <hostname>:9102/stats?consumerFilter=planner
    4. If there are multiple hosts in the index map for the selected index, aggregate the items count across host 
    5. Run a count(*) query against the collection to get the KV item count
    6. Compare result from 4 & 5 and raiseException if not matching 
    """

    def item_count_check(self, sample_size=5):
        # Get all index nodes in the cluster
        idx_node_list = self.find_nodes_with_service(self.get_services_map(), "index")
        idx_node_list.sort()

        # Get Index Map for indexes in the bucket
        index_map = self.get_index_map(self.bucket_name, idx_node_list[0])

        if len(index_map) == 0:
            self.log.info("Item check count not possible, no indexes present for the given bucket.")
            return

        # Randomly choose indexes on which item count check has to be performed
        item_count_check_indexes = random.sample(index_map, min(sample_size, len(index_map)))

        errors = []

        for index in item_count_check_indexes:
            # Exclude any indexes that have when or where clause in the index definition from item count check
            # as the item count will never match the number of docs in collection because of the partial index.
            # Currently it is idx8 that has a when / where clause in the index definition
            if index["name"].split("_")[0] == "idx8":
                continue

            if (index["scope"] != "_default" and index["collection"] != "_default"):
                keyspace_path = index["bucket"] + ":" + index["scope"] + ":" + index["collection"] + ":"
            else:
                keyspace_path = index["bucket"] + ":"
            stat_key = keyspace_path + index["name"] + ":docid_count"
            alt_stat_key = keyspace_path + index["name"] + ":items_count"
            pending_mutations_key = keyspace_path + index["name"] + ":num_docs_pending"
            keyspace_name_for_query = "`" + index["bucket"] + "`.`" + index["scope"] + "`.`" + index["collection"] + "`"

            index_item_count = 0
            index_pending_mutations = 0
            for host in index["hosts"]:
                item_count, pending_mutations = self.get_stats(stat_key, alt_stat_key, pending_mutations_key,
                                                               host.split(":")[0])
                if item_count >= 0:
                    index_item_count += item_count
                    index_pending_mutations += pending_mutations
                else:
                    self.log.info("Got an error retrieving stat {0} or {1} from {2}".format(stat_key, alt_stat_key,
                                                                                            host.split(":")[0]))
                    errors_obj = {}
                    errors_obj["type"] = "error_retrieving_stats"
                    errors_obj["index_name"] = index["name"]
                    errors_obj["keyspace"] = keyspace_name_for_query
                    errors.append(errors_obj)

            # Get Collection item count from KV via N1QL
            kv_item_count = -1
            kv_item_count_query = "select raw count(*) from {0};".format(keyspace_name_for_query)
            status, results, queryResult = self._execute_query(kv_item_count_query)
            if status is not None:
                for result in results:
                    self.log.debug(result)
                    kv_item_count = result
            else:
                self.log.info("Got an error retrieving stat from query via n1ql with query - {0}. Status : {1} ".format(
                    kv_item_count_query, status))
                errors_obj = {}
                errors_obj["type"] = "error_retrieving_stats_from_kv_via_n1ql"
                errors_obj["index_name"] = index["name"]
                errors_obj["keyspace"] = keyspace_name_for_query
                errors.append(errors_obj)

            self.log.info(
                "Item count for index {0} on {1} is {2}. Pending Mutations = {3} Total items in collection are {4}".format(index["name"],
                                                                                                   keyspace_name_for_query,
                                                                                                   index_item_count, index_pending_mutations,
                                                                                                   kv_item_count))
            if int(index_item_count) != int(kv_item_count):
                errors_obj = {}
                errors_obj["type"] = "item_count_check_failed"
                errors_obj["index_name"] = index["name"]
                errors_obj["keyspace"] = keyspace_name_for_query
                errors_obj["index_item_count"] = index_item_count
                errors_obj["index_pending_mutations"] = index_pending_mutations
                errors_obj["kv_item_count"] = kv_item_count
                errors.append(errors_obj)

        if len(errors) > 0:
            raise Exception("There were errors in the item count check phase - \n{0}".format(errors))
        else:
            self.log.info("Item check count passed. No discrepancies seen.")

    def get_stats(self, stat_key, alt_stat_key, pending_mutations_key, index_node_addr, index_node_port=9102):
        endpoint = "http://" + index_node_addr + ":" + str(index_node_port) + "/stats"

        retry_count = 3
        while retry_count > 1:
            try:
                # Get index stats from the indexer node
                response = requests.get(endpoint, auth=(
                    self.username, self.password), verify=True, )
                need_retry = False
                if response.ok:
                    response = json.loads(response.text)
                    if stat_key in response:
                        item_count = int(response[stat_key])
                    else:
                        if alt_stat_key in response:
                            item_count = int(response[alt_stat_key])
                        else:
                            self.log.info(
                                "Stat {0} or {1} not found in stats output for host {2}".format(stat_key, alt_stat_key,
                                                                                                index_node_addr))
                            need_retry = True

                    if pending_mutations_key in response:
                        pending_mutations = int(response[pending_mutations_key])
                    else:
                        self.log.info("Stat {0} not found in stats output for host {1}".format(pending_mutations_key,
                                                                                               index_node_addr))
                        need_retry = True

                else:
                    self.log.info("Stat endpoint request status was not 200 : {0}".format(response))
                    need_retry = True

                if need_retry :
                    retry_count = retry_count - 1
                    if retry_count > 1:
                        self.log.info("Retrying fetching stats. Retries left = {0}".format(str(retry_count)))
                    else:
                        return -1, -1

                else:
                    # return item_count, pending_mutations
                    return item_count, pending_mutations

            except requests.exceptions.HTTPError as errh:
                self.log.error("HTTPError getting response from /stats : {0}".format(str(errh)))
            except requests.exceptions.ConnectionError as errc:
                self.log.error("ConnectionError getting response from /stats : {0}".format(str(errc)))
            except requests.exceptions.Timeout as errt:
                self.log.error("Timeout getting response from /stats : {0}".format(str(errt)))
            except requests.exceptions.RequestException as err:
                self.log.error("Error getting response from /stats : {0}".format(str(err)))

    """
    Determine number of index nodes in the cluster and set max num replica accordingly.
    """

    def set_max_num_replica(self):
        nodelist = self.find_nodes_with_service(self.get_services_map(), "index")
        if len(nodelist) > 4:
            self.max_num_replica = 3
        else:
            self.max_num_replica = len(nodelist) - 1  # Max num replica = number of idx nodes in cluster - 1
        self.log.info("Setting Max Replica for this test to : {0}".format(self.max_num_replica))

    """
    Return the index map for the specified bucket
    """

    def get_index_map(self, bucket, index_node_addr, index_node_port=9102):
        endpoint = "http://" + index_node_addr + ":" + str(index_node_port) + "/getIndexStatus"
        # Get map of indexes in the cluster
        response = requests.get(endpoint, auth=(
            self.username, self.password), verify=True, )

        idx_map = []

        if (response.ok):
            response = json.loads(response.text)
            for index in response["status"]:
                if index["bucket"] == bucket:
                    idx_map.append(index)

        return idx_map

    """
    Populate the service map for all nodes in the cluster.
    """

    def get_services_map(self):
        cluster_url = "http://" + self.node_addr + ":" + self.node_port + "/pools/default"
        node_map = []

        try:
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

        except requests.exceptions.HTTPError as errh:
            self.log.error("HTTPError getting response from {1} : {0}".format(str(errh), cluster_url))
        except requests.exceptions.ConnectionError as errc:
            self.log.error("ConnectionError getting response from {1} : {0}".format(str(errc), cluster_url))
        except requests.exceptions.Timeout as errt:
            self.log.error("Timeout getting response from {1} : {0}".format(str(errt), cluster_url))
        except requests.exceptions.RequestException as err:
            self.log.error("Error getting response from {1} : {0}".format(str(err), cluster_url))

        return node_map

    """
    Create n number of UDF on all scopes of a given bucket
    """

    def create_udfs(self):
        cb_scopes = self.cb.collections().get_all_scopes()
        scope_name_list = []
        for scope in cb_scopes:
            scope_name_list.append("`" + self.bucket_name + "`.`" + scope.name + "`")
        self.log.info(str(scope_name_list))

        # Create JS function
        self.log.info("Create JS Function")
        query_node = self.find_nodes_with_service(self.get_services_map(), "n1ql")[0]
        api1 = "http://" + query_node + ':8093/functions/v1/libraries/math/functions/add'
        data1 = {"name": "add", "code": "function add(a, b) { let data = a + b; return data; }"}

        api2 = "http://" + query_node + ':8093/functions/v1/libraries/math/functions/sub'
        data2 = {"name": "add", "code": "function sub(a, b) { let data = a - b; return data; }"}

        api3 = "http://" + query_node + ':8093/functions/v1/libraries/math/functions/mul'
        data3 = {"name": "add", "code": "function mul(a, b) { let data = a * b; return data; }"}

        api4 = "http://" + query_node + ':8093/functions/v1/libraries/math/functions/div'
        data4 = {"name": "add", "code": "function div(a, b) { let data = a / b; return data; }"}

        auth = (self.username, self.password)
        try:
            response = requests.get(url=api1, auth=auth, data=data1, timeout=120)
            if response.status_code == 200:
                return response.json()

            response = requests.get(url=api2, auth=auth, data=data2, timeout=120)
            if response.status_code == 200:
                return response.json()

            response = requests.get(url=api3, auth=auth, data=data3, timeout=120)
            if response.status_code == 200:
                return response.json()

            response = requests.get(url=api4, auth=auth, data=data4, timeout=120)
            if response.status_code == 200:
                return response.json()

        except requests.exceptions.HTTPError as errh:
            self.log.error("HTTPError getting response from /functions : {0}".format(str(errh)))
        except requests.exceptions.ConnectionError as errc:
            self.log.error("ConnectionError getting response from /functions : {0}".format(str(errc)))
        except requests.exceptions.Timeout as errt:
            self.log.error("Timeout getting response from /functions : {0}".format(str(errt)))
        except requests.exceptions.RequestException as err:
            self.log.error("Error getting response from /functions : {0}".format(str(err)))

        udf_statement_templates = [

            "CREATE FUNCTION default:keyspace_placeholder.fun1_suffix(arg1, arg2){arg1 + arg2}",
            "CREATE FUNCTION default:keyspace_placeholder.fun2_suffix(a, b) LANGUAGE javascript AS \"add\" AT \"math\"",
            "CREATE FUNCTION default:keyspace_placeholder.fun3_suffix(arg1, arg2){arg1 - arg2}",
            "CREATE FUNCTION default:keyspace_placeholder.fun4_suffix(a, b) LANGUAGE javascript AS \"sub\" AT \"math\"",
            "CREATE FUNCTION default:keyspace_placeholder.fun5_suffix(arg1, arg2){arg1 * arg2}",
            "CREATE FUNCTION default:keyspace_placeholder.fun6_suffix(a, b) LANGUAGE javascript AS \"mul\" AT \"math\"",
            "CREATE FUNCTION default:keyspace_placeholder.fun7_suffix(arg1, arg2){arg1 / arg2}",
            "CREATE FUNCTION default:keyspace_placeholder.fun8_suffix(a, b) LANGUAGE javascript AS \"div\" AT \"math\""
        ]
        for scope in scope_name_list:

            for i in range(self.num_udf_per_scope):
                udf_stmt = random.choice(udf_statement_templates).replace("keyspace_placeholder", scope)
                udf_stmt = udf_stmt.replace("suffix", ''.join(random.choices(string.ascii_uppercase +
                                                                             string.digits, k=6)))

                status, results, queryResult = self._execute_query(udf_stmt)
                self.log.info(udf_stmt + " : " + str(status))
                sleep(0.25)

    """
    Drop all UDFs
    """

    def drop_all_udfs(self):
        drop_function_gen_template = "select raw 'DROP FUNCTION default:`' || identity.`bucket`|| '`.`' || identity.`scope`|| '`.`' || identity.name || '`' from system:functions;"

        self.log.info("Starting to drop all functions ")

        status, results, queryResult = self._execute_query(drop_function_gen_template)
        if status is not None:
            for result in results:
                drop_status, _, _ = self._execute_query(result)

                # Sleep for 0.25 secs after dropping an index
                sleep(0.25)
        self.log.info("Drop all functions completed")

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
                if counter >= 10:
                    # Wait for all indexes to be built
                    indexes_built = self.wait_for_indexes_to_be_built(keyspace_batch)
                    if not indexes_built:
                        self.log.error("All indexes not built until timed out")
                        break
                    counter = 0
                    keyspace_batch.clear()

                build_index_query = build_index_query_template.replace("keyspacename", keyspace)
                self.log.info("Building indexes for keyspace : {0}".format(keyspace))
                self.log.info("Query used = {0}".format(build_index_query))

                status, results, queryResult = self._execute_query(build_index_query)
                counter += 1
                keyspace_batch.append(keyspace)

                # Sleep for 2 secs after issuing a build index for all indexes for a collection
                sleep(2)
            else:
                build_index_query = build_index_query_template.replace("keyspacename", keyspace)
                self.log.info("Building indexes for keyspace : {0}".format(keyspace))
                self.log.debug("Query used = {0}".format(build_index_query))

                status, results, queryResult = self._execute_query(build_index_query)

                # Sleep for 2 secs after issuing a build index for all indexes for a collection
                sleep(2)

        self.log.info("Building all deferred indexes completed ")

    """
    Drop all indexes in the cluster
    """

    def drop_all_indexes(self, keyspace_name_list, validate=True):
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
        if validate:
            index_map_from_system_indexes = self.get_index_map_from_system_indexes()
            for keyspace in keyspace_name_list:
                keyspace = keyspace.replace('`', '')
                if keyspace in index_map_from_system_indexes:
                    self.log.error(f"All indexes not dropped for keyspace:{keyspace}")
            self.log.info("Validation completed")

    """
    Drop random indexes in a loop
    """

    def drop_indexes_in_a_loop(self, timeout, interval):
        # Establish timeout. If timeout > 0, run in infinite loop
        end_time = 0
        if timeout > 0:
            end_time = time.time() + timeout
        while True:
            random.seed(datetime.now())

            drop_random_index_query_gen = "SELECT RAW 'DROP INDEX `' || name || '` on `' || bucket_id || '`.`' || scope_id || '`.`' || keyspace_id || '`;'  FROM system:all_indexes where bucket_id='{0}' limit 1".format(
                self.bucket_name)

            status, results, queryResult = self._execute_query(drop_random_index_query_gen)
            if status is not None and len(results) > 0:
                for result in results:
                    drop_status, _, _ = self._execute_query(result)

                    # Sleep for 2 secs after dropping an index
                    sleep(2)
            else:
                pass

            # Exit if timed out
            if timeout > 0 and time.time() > end_time:
                break

            # Wait for the interval before doing the next CRUD operation
            sleep(interval)

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
            query = index_status_check_query_template.replace("keyspace_name_list", str(keyspace_name_list))
            self.log.info("Wait query : {0}".format(query))
            status, result, queryResult = self._execute_query(query)
            self.log.info("Result = {0}".format(str(result)))
            if result[0] == 0:
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
            queryResult = self.cluster.query(statement, QueryOptions(timeout=timeout))
            try:
                status = queryResult.metadata().status()
                results = queryResult.rows()
            except:
                self.log.info("Query didnt return status or results")
                self.log.error("Unexpected error :", sys.exc_info()[0])
                pass

        except couchbase.exceptions.QueryException as qerr:
            self.log.debug("qerr")
            self.log.error(qerr)
        except couchbase.exceptions.HTTPException as herr:
            self.log.debug("herr")
            self.log.error(herr)
        except couchbase.exceptions.QueryIndexAlreadyExistsException as qiaeerr:
            self.log.debug("qiaeerr")
            self.log.error(qiaeerr)
        except couchbase.exceptions.TimeoutException as terr:
            self.log.debug("terr")
            self.log.error(terr)
        except:
            self.log.error("Unexpected error :", sys.exc_info()[0])

        return status, results, queryResult

    def get_indexer_metadata(self, timeout=120):
        self.log.info("polling /getIndexStatus")
        idx_node = self.find_nodes_with_service(self.get_services_map(), "index")[0]
        api = "http://" + idx_node + ':9102/getIndexStatus'
        auth = (self.username, self.password)
        try:
            response = requests.get(url=api, auth=auth, timeout=timeout)
            if response.status_code == 200:
                return response.json()

        except requests.exceptions.HTTPError as errh:
            self.log.error("HTTPError getting response from /getIndexStatus : {0}".format(str(errh)))
        except requests.exceptions.ConnectionError as errc:
            self.log.error("ConnectionError getting response from /getIndexStatus : {0}".format(str(errc)))
        except requests.exceptions.Timeout as errt:
            self.log.error("Timeout getting response from /getIndexStatus : {0}".format(str(errt)))
        except requests.exceptions.RequestException as err:
            self.log.error("Error getting response from /getIndexStatus : {0}".format(str(err)))

    def wait_until_indexes_online(self, timeout=60, defer_build=False, check_paused_index=False):
        init_time = time.time()
        check = False
        while not check:
            index_metadata = self.get_indexer_metadata()
            if 'status' not in index_metadata:
                return True
            index_status = index_metadata['status']
            next_time = time.time()
            for index_state in index_status:
                if defer_build:
                    if index_state["status"] == "Ready" or index_state["status"] == "Created":
                        check = True
                    else:
                        check = False
                        sleep(1)
                        break
                elif check_paused_index:
                    if index_state["status"] == "Paused":
                        check = True
                    else:
                        check = False
                        sleep(1)
                        break
                else:
                    if index_state["status"] == "Ready":
                        check = True
                    else:
                        check = False
                        sleep(1)
                        break
            if next_time - init_time > timeout:
                check = False
                break
        return check


class NestedDict(dict):
    """Implementation of perl's autovivification feature."""

    def __getitem__(self, item):
        try:
            return dict.__getitem__(self, item)
        except KeyError:
            value = self[item] = type(self)()
            return value


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
        indexMgr.create_indexes_on_bucket(keyspace_name_list, indexMgr.validate)
    elif indexMgr.action == "build_deferred_index":
        indexMgr.build_all_deferred_indexes(keyspace_name_list, indexMgr.max_num_collections)
        # The SDK way to build all deferred indexes is not yet working in Python SDK 3.0.4. To revisit once implemented.
        # indexMgr.build_all_deferred_indexes_sdk(keyspace_name_list)
    elif indexMgr.action == "drop_all_indexes":
        indexMgr.drop_all_indexes(keyspace_name_list, indexMgr.validate)
    elif indexMgr.action == "create_index_loop":
        indexMgr.create_indexes_on_bucket_in_a_loop(indexMgr.timeout, indexMgr.interval)
    elif indexMgr.action == "alter_indexes":
        indexMgr.alter_indexes(indexMgr.timeout, indexMgr.interval)
    elif indexMgr.action == "enable_cbo":
        indexMgr.enable_cbo_and_update_statistics(indexMgr.cbo_enable_ratio)
    elif indexMgr.action == "delete_statistics":
        indexMgr.delete_statistics()
    elif indexMgr.action == "drop_index_loop":
        indexMgr.drop_indexes_in_a_loop(indexMgr.timeout, indexMgr.interval)
    elif indexMgr.action == "item_count_check":
        indexMgr.item_count_check(indexMgr.sample_size)
    elif indexMgr.action == "random_recovery":
        indexMgr.random_recovery(indexMgr.timeout, indexMgr.interval)
    elif indexMgr.action == "create_udf":
        indexMgr.create_udfs()
    elif indexMgr.action == "drop_udf":
        indexMgr.drop_all_udfs()
    else:
        print("Invalid choice for action. Choose from the following - "
              "create_index | build_deferred_index | drop_all_indexes | create_index_loop | alter_indexes | enable_cbo | drop_index_loop | item_count_check | random_recovery | create_udf | drop_udf")

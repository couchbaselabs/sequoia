import json
import string
import sys
import threading
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
from couchbase.management.collections import CollectionSpec
import dns.resolver
import boto3
from collections import defaultdict
import re
from beautifultable import BeautifulTable
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
    # Regular indexes
    {"indexname": "idx1",
     "is_vector": False,
     "validate_item_count_check": False,
     "statement": "CREATE INDEX `idx1_idxprefix` ON keyspacenameplaceholder(country, DISTINCT ARRAY `r`.`ratings`.`Check in / front desk` FOR r in `reviews` END,array_count((`public_likes`)),array_count((`reviews`)) DESC,`type`,`phone`,`price`,`email`,`address`,`name`,`url`) "},
    {"indexname": "idx2",
     "is_vector": False,
     "validate_item_count_check": True,
     "statement": "CREATE INDEX `idx2_idxprefix` ON keyspacenameplaceholder(`free_breakfast`,`type`,`free_parking`,array_count((`public_likes`)),`price`,`country`)"},
    {"indexname": "idx3",
     "is_vector": False,
     "validate_item_count_check": True,
     "statement": "CREATE INDEX `idx3_idxprefix` ON keyspacenameplaceholder(`free_breakfast`,`free_parking`,`country`,`city`) "},
    {"indexname": "idx4",
     "is_vector": False,
     "validate_item_count_check": True,
     "statement": "CREATE INDEX `idx4_idxprefix` ON keyspacenameplaceholder(`price`,`city`,`name`)"},
    {"indexname": "idx5",
     "is_vector": False,
     "validate_item_count_check": False,
     "statement": "CREATE INDEX `idx5_idxprefix` ON keyspacenameplaceholder(ALL ARRAY `r`.`ratings`.`Rooms` FOR r IN `reviews` END,`avg_rating`)"},
    {"indexname": "idx6",
     "is_vector": False,
     "validate_item_count_check": True,
     "statement": "CREATE INDEX `idx6_idxprefix` ON keyspacenameplaceholder(`city`)"},
    {"indexname": "idx7",
     "is_vector": False,
     "validate_item_count_check": True,
     "statement": "CREATE INDEX `idx7_idxprefix` ON keyspacenameplaceholder(`price`,`name`,`city`,`country`)"},
    
    # New indexes
    {"indexname": "idx8",
     "is_vector": False,
     "validate_item_count_check": False,
     "statement": "CREATE INDEX `idx8_idxprefix` ON keyspacenameplaceholder(DISTINCT ARRAY FLATTEN_KEYS(`r`.`author`,`r`.`ratings`.`Cleanliness`) FOR r IN `reviews` when `r`.`ratings`.`Cleanliness` < 4 END, `country`, `email`, `free_parking`)"},
    {"indexname": "idx9",
     "is_vector": False,
     "validate_item_count_check": False,
     "statement": "CREATE INDEX `idx9_idxprefix` ON keyspacenameplaceholder(ALL ARRAY FLATTEN_KEYS(`r`.`author`,`r`.`ratings`.`Rooms`) FOR r IN `reviews` END, `free_parking`)"},
    {"indexname": "idx10",
     "is_vector": False,
     "validate_item_count_check": False,
     "statement": "CREATE INDEX `idx10_idxprefix` ON keyspacenameplaceholder((ALL (ARRAY(ALL (ARRAY flatten_keys(n,v) FOR n:v IN (`r`.`ratings`) END)) FOR `r` IN `reviews` END)))"},
    {"indexname": "idx11",
     "is_vector": False,
     "validate_item_count_check": False,
     "statement": "CREATE INDEX `idx11_idxprefix` ON keyspacenameplaceholder(ALL ARRAY FLATTEN_KEYS(`r`.`ratings`.`Rooms`,`r`.`ratings`.`Cleanliness`) FOR r IN `reviews` END, `email`, `free_parking`)"},
    {"indexname": "idx12",
     "is_vector": False,
     "validate_item_count_check": True,
     "statement": "CREATE INDEX `idx12_idxprefix` ON keyspacenameplaceholder(`name` INCLUDE MISSING DESC,`phone`,`type`)"},
    {"indexname": "idx13",
     "is_vector": False,
     "validate_item_count_check": True,
     "statement": "CREATE INDEX `idx13_idxprefix` ON keyspacenameplaceholder(`city` INCLUDE MISSING ASC, `phone`)"},

    # Vector indexes  
    {"indexname": "idxvector1",
     "is_vector": True,
     "validate_item_count_check": True,
     "statement": "CREATE INDEX `idxvector1_idxprefix` ON keyspacenameplaceholder(`free_breakfast`,vectors VECTOR, `free_parking`,`country`,`city`) "},
    {"indexname": "idxvector2",
     "is_vector": True,
     "validate_item_count_check": True,
     "statement": "CREATE INDEX `idxvector2_idxprefix` ON keyspacenameplaceholder(`price`,`city`,`name`, vectors VECTOR)"},
    {"indexname": "idxvector3",
     "validate_item_count_check": True,
     "is_vector": True,
     "statement": "CREATE INDEX `idxvector3_idxprefix` ON keyspacenameplaceholder(`name` INCLUDE MISSING DESC,`phone`,`type`, vectors VECTOR)"},
    {"indexname": "idxvector4",
     "is_vector": True,
     "validate_item_count_check": True,
     "statement": "CREATE INDEX `idxvector4_idxprefix` ON keyspacenameplaceholder(country,vectors VECTOR)"},
    {"indexname": "idxvector5",
     "is_vector": True,
     "vector_leading": True,
     "validate_item_count_check": True,
     "statement": "CREATE INDEX `idxvector5_idxprefix` ON keyspacenameplaceholder(vectors VECTOR)"},
    {"indexname": "idxvector6",
     "is_vector": True,
     "vector_leading": True,
     "validate_item_count_check": True,
     "statement": "CREATE INDEX `idxvector6_idxprefix` ON keyspacenameplaceholder(vectors VECTOR, city )"},
    #  {"indexname": "idxvector7",
    #   "is_vector": True,
    #   "validate_item_count_check": True,
    #   "statement": "CREATE INDEX `idxvector7_idxprefix` ON keyspacenameplaceholder(vectors VECTOR, country) where city=\"Arnettamouth\""},

    # BHIVE indexes
    {"indexname": "bhiveidxvector1",
     "validate_item_count_check": True,
     "is_vector": True,
     "vector_leading": True,
     "statement": "CREATE VECTOR INDEX `idxbhive1_idxprefix` ON keyspacenameplaceholder(vectors VECTOR) INCLUDE (price, avg_rating, free_breakfast)"},
    {"indexname": "bhiveidxvector2",
     "validate_item_count_check": True,
     "is_vector": True,
     "vector_leading": True,
     "statement": "CREATE VECTOR INDEX `idxbhive2_idxprefix` ON keyspacenameplaceholder(vectors VECTOR) INCLUDE (city, country)"},
     # {"indexname": "bhiveidxvector3",
    #  "is_vector": True,
    #  "validate_item_count_check": True,
    #  "statement": "CREATE VECTOR INDEX `idxbhive3_idxprefix` ON keyspacenameplaceholder(vectors VECTOR) where city=\"Arnettamouth\""}

]

SHOES_INDEX_TEMPLATES = [
    # vector indexes
    {"indexname": "composite_shoes_idx",
     "is_vector": True,
     "validate_item_count_check": True,
     "statement": "CREATE INDEX composite_shoes1_idxprefix ON keyspacenameplaceholder(`category`,`country`, `embedding` VECTOR) "},
    {"indexname": "composite_shoes_idx2",
     "is_vector": True,
     "validate_item_count_check": True,
     "statement": "CREATE INDEX composite_shoes2_idxprefix ON keyspacenameplaceholder( `brand`, `color`, `embedding` VECTOR) "},
    {"indexname": "composite_shoes_idx3",
     "is_vector": True,
     "validate_item_count_check": True,
     "statement": "CREATE INDEX composite_shoes3_idxprefix ON keyspacenameplaceholder(`size`, `embedding` VECTOR) "},
     
    # BHIVE indexes 
    {"indexname": "bhive_shoes_idx1",
     "is_vector": True,
     "validate_item_count_check": True,
     "vector_leading": True,
     "statement": "CREATE VECTOR INDEX idxbhive1_shoes_idxprefix ON keyspacenameplaceholder(`embedding` VECTOR) INCLUDE (`category`)"},
    {"indexname": "bhive_shoes_idx2",
     "is_vector": True,
     "vector_leading": True,
     "validate_item_count_check": True,
     "statement": "CREATE VECTOR INDEX idxbhive2_shoes_idxprefix ON keyspacenameplaceholder(`embedding` VECTOR) INCLUDE (`country`)"},
    {"indexname": "bhive_shoes_idx3",
     "is_vector": True,
     "vector_leading": True,
     "validate_item_count_check": True,
     "statement": "CREATE VECTOR INDEX idxbhive3_shoes_idxprefix ON keyspacenameplaceholder(`embedding` VECTOR) INCLUDE (`brand`, `color`)"},
    {"indexname": "bhive_shoes_idx4",
     "is_vector": True,
     "vector_leading": True,
     "validate_item_count_check": True,
     "statement": "CREATE VECTOR INDEX idxbhive4_shoes_idxprefix ON keyspacenameplaceholder(`embedding` VECTOR) INCLUDE (`size`)"}
]

DISTANCE_SUPPORTED_FUNCTIONS = ["L2", "L2_SQUARED", "DOT", "COSINE", "EUCLIDEAN", "EUCLIDEAN_SQUARED"]
DESCRIPTION_LIST = ["IVF,PQ8x8", "IVF,SQ8", "IVF,PQ128x8", "IVF,PQ64x8", "IVF,PQ32x8", "IVF,PQ32x4FS", "IVF,SQfp16"]
SCAN_NPROBE_MIN = 5
SCAN_NPROBE_MAX = 20


class IndexManager:

    def __init__(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("-n", "--node", help="Couchbase Server Node Address")
        parser.add_argument("-nl", "--node_list", help="Used to directly interact with the node", default="")
        parser.add_argument("-c", "--capella", help="Set to True if tests need to run on Capella", default=False)
        parser.add_argument("-x", "--tls", help="Set to True if tests need to run with TLS enabled", default=False)
        parser.add_argument("-o", "--port", help="Couchbase Server Node Port")
        parser.add_argument("-u", "--username", help="Couchbase Server Cluster Username")
        parser.add_argument("-p", "--password", help="Couchbase Server Cluster Password")
        parser.add_argument("-b", "--bucket", help="Bucket name on which indexes are to be created")
        parser.add_argument("-i", "--num_index_per_collection", type=int,
                            help="Number of indexes to be created per collection of bucket, if action = create_index. "
                                 "If action=drop_index, number of indexes to be dropped per collection of bucket")
        parser.add_argument("-d", "--dataset", help="Dataset to be used for the test. Choices are - hotel",
                            default="hotel")
        parser.add_argument("--user_specified_prefix", help="Use this prefix to append to index name creation",
                            default="")
        parser.add_argument("--allow_equivalent_indexes",
                            help="Enable this flag if you want to create equivalent indexes across bucket",
                            default=False)
        parser.add_argument("-a", "--action",
                            choices=["create_index", "build_deferred_index", "drop_all_indexes", "create_index_loop",
                                     "drop_index_loop", "alter_indexes", "enable_cbo", "delete_statistics",
                                     "item_count_check", "post_topology_change_validations", "replica_count_check",
                                     "random_recovery", "create_udf", "drop_udf", "create_n1ql_udf",
                                     "validate_tenant_affinity", "set_fast_rebalance_config",
                                     "create_n_indexes_on_buckets", "validate_s3_cleanup", "copy_aws_keys",
                                     "cleanup_s3", "poll_total_requests_during_rebalance",
                                     "wait_until_rebalance_cleanup_done", "print_stats",
                                     "wait_until_mutations_processed", "random_index_lifecycle"],
                            help="Choose an action to be performed. Valid actions : create_index | build_deferred_index | drop_all_indexes | create_index_loop | "
                                 "drop_index_loop | alter_indexes | enable_cbo | delete_statistics | replica_count_check "
                                 "| item_count_check | random_recovery | create_udf | drop_udf | create_n1ql_udf | post_topology_change_validations"
                                 "| validate_tenant_affinity | set_fast_rebalance_config | create_n_indexes_on_buckets "
                                 "| copy_aws_keys | cleanup_s3 | validate_s3_cleanup | poll_total_requests_during_rebalance | wait_until_rebalance_cleanup_done | print_stats | wait_until_mutations_processed",
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
        parser.add_argument("--lib_filename", help="Filename for N1QL JS UDF Library", default=None)
        parser.add_argument("--lib_name", help="Name for the N1QL JS UDF Library to be created", default=None)
        parser.add_argument("--aws_access_key_id", help="AWS access key ID for fast rebalance")
        parser.add_argument("--aws_secret_access_key", help="AWS secret key for fast rebalance")
        parser.add_argument("--region", help="AWS region for fast rebalance", default="us-west-1")
        parser.add_argument("--s3_bucket", help="S3 bucket used for fast rebalance", default="gsi-system-test-onprem-2")
        parser.add_argument("--storage_prefix", help="Storage prefix for S3 bucket used for fast rebalance",
                            default="indexing-system-test")
        parser.add_argument("--bucket_list", help="List of buckets to be used for index creation")
        parser.add_argument("--use_custom_keyspace",
                            help="if create_n_indexes_on_bucket needs to use a specific keyspace")
        parser.add_argument("--num_of_indexes_per_bucket", type=int, default=20,
                            help="Number of indexes per bucket you want to create")
        parser.add_argument("--limit_total_index_count_in_cluster", type=int, default=10000,
                            help="Number of indexes per bucket you want to create")
        parser.add_argument("--num_of_batches", default=None, help="Number of batch of indexes to be created")
        parser.add_argument("--sleep_before_polling", default=None,
                            help="Duration (in seconds) to sleep before polling for total requests")
        parser.add_argument("--capella_cluster_id", default=None)
        parser.add_argument("--sbx", default=None)
        parser.add_argument("--token", default=None)
        parser.add_argument("--skip_default_collection", default="true")
        parser.add_argument("-vec", "--create_vector_indexes", help="create_vector_indexes")
        parser.add_argument("-bhi", "--create_bhive_indexes", help="create_bhive_indexes")
        parser.add_argument("-da", "--distance_algo", help="distance algorithm", default=None)
        parser.add_argument("-num_dimensions", "--num_dimensions", type=int, default=128, help="Num of dimensions")
        parser.add_argument("--num_vectors", type=int, default=1000000,
                            help="Number of indexes per bucket you want to create")
        parser.add_argument("--base64_encoding_vectors", default="false",
                            help="are vector embeddings base64 encoded?")
        parser.add_argument("--defer_build", default="false",
                            help="are indexes to be deferred?")
        parser.add_argument("--use_description", default="false",
                            help="use specific description to create vector indexes")
        parser.add_argument("--xattrs_vectors", default="false",
                            help="are vector embeddings part of xattrs?")
        parser.add_argument("--set_max_replicas", default=None,
                            help="max replica count for indexes")
        parser.add_argument("--all_docs_indexed", default="false",
                            help="have all mutations been processed?")
        parser.add_argument("--log_level",
                          choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                          default="INFO",
                          help="Set the logging level")
        args = parser.parse_args()
        self.log = logging.getLogger("indexmanager")
        self.log.setLevel(getattr(logging, args.log_level))
        self.node_addr = args.node
        self.node_list = args.node_list.split(",")
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
        self.aws_access_key_id = args.aws_access_key_id
        self.s3_bucket = args.s3_bucket
        self.storage_prefix = args.storage_prefix
        self.user_specified_prefix = args.user_specified_prefix
        self.allow_equivalent_indexes = args.allow_equivalent_indexes
        self.aws_secret_access_key = args.aws_secret_access_key
        self.region = args.region
        self.num_of_indexes_per_bucket = args.num_of_indexes_per_bucket
        self.limit_total_index_count_in_cluster = args.limit_total_index_count_in_cluster
        self.num_of_batches = args.num_of_batches
        self.sleep_before_polling = args.sleep_before_polling
        self.capella_cluster_id = args.capella_cluster_id
        self.sbx = args.sbx
        self.num_vectors = args.num_vectors
        self.base64_encoding = args.base64_encoding_vectors == 'true'
        self.xattrs = args.xattrs_vectors == 'true'
        self.token = args.token
        self.distance_algo = args.distance_algo
        self.defer_build = args.defer_build == 'true'
        self.all_docs_indexed = args.all_docs_indexed == 'true'
        if args.use_description != 'false':
            self.use_description = args.use_description
        else:
            self.use_description = None
        self.skip_default_collection = True if args.skip_default_collection == 'true' else False
        self.use_custom_keyspace = args.use_custom_keyspace
        if self.cbo_enable_ratio > 100:
            self.cbo_enable_ratio = 25
        self.cbo_interval = args.cbo_interval
        self.sample_size = args.sample_size
        self.num_udf_per_scope = args.num_udf_per_scope
        self.disable_partitioned_indexes = args.no_partitioned_indexes
        self.create_query_node_pattern = r"create .*?index (.*?) on .*?nodes':.*?\[(.*?)].*?$"
        if args.set_max_replicas:
            self.set_max_replicas = int(args.set_max_replicas)
        else:
            self.set_max_replicas = None
        if args.lib_filename:
            self.lib_filename = "./" + args.lib_filename
        else:
            self.lib_filename = None
        self.lib_name = args.lib_name
        self.use_tls = args.tls
        self.capella_run = args.capella
        self.use_https = False
        self.create_vector_indexes = args.create_vector_indexes == 'true'
        self.create_bhive_indexes = args.create_bhive_indexes == 'true'
        self.num_dimensions = args.num_dimensions
        self.use_tls = args.tls == 'true' or args.tls is True
        self.capella_run = args.capella == 'true' or args.capella is True
        self.use_https = False
        print("Capella run is set to {} and TLS is set to {}".format(self.capella_run, self.use_tls))
        if self.use_tls or self.capella_run:
            self.node_port_index = '19102'
            self.node_port_query = '18093'
            self.port = '18091'
            self.scheme = "https"
            self.use_https = True
            if self.capella_run:
                self.rest_url = self.fetch_rest_url(self.node_addr)
                self.index_url = "{}://".format(self.scheme) + self.rest_url + ":" + self.node_port_index
                self.url = "{}://".format(self.scheme) + self.rest_url + ":" + self.port
            else:
                self.index_url = "{}://".format(self.scheme) + self.node_addr + ":" + self.node_port_index
                self.url = "{}://".format(self.scheme) + self.node_addr + ":" + self.port
        else:
            self.node_port_index = '9102'
            self.port = '8091'
            self.node_port_query = '8093'
            self.scheme = "http"
            self.index_url = "{}://".format(self.scheme) + self.node_addr + ":" + self.node_port_index
            self.url = "{}://".format(self.scheme) + self.node_addr + ":" + self.port
        HOTEL_DS_CBO_FIELDS = "`country`, DISTINCT ARRAY `r`.`ratings`.`Check in / front desk`, array_count((`public_likes`)),array_count((`reviews`)) DESC,`type`,`phone`,`price`,`email`,`address`,`name`,`url`,`free_breakfast`,`free_parking`,`city`"
        self.cbo_fields = HOTEL_DS_CBO_FIELDS
        # Initialize connections to the cluster
        # Logging configuration
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
        # If there are more datasets supported, this can be expanded.
        self.idx_def_templates = []
        if self.dataset == "hotel":
            template_list = HOTEL_DS_INDEX_TEMPLATES
        elif self.dataset == "shoes":
            template_list = SHOES_INDEX_TEMPLATES
        else:
            raise ValueError(f"Dataset {self.dataset} is not supported")
        for template in template_list:
            # Include non-vector indexes by default
            is_scalar = not (self.create_bhive_indexes or self.create_vector_indexes)
            if is_scalar and not template['is_vector']:
                self.idx_def_templates.append(template)
            # Include vector indexes if flag is set
            elif self.create_vector_indexes and template['is_vector'] and not template['indexname'].startswith('bhive'):
                self.idx_def_templates.append(template)
            # Include BHIVE indexes if flag is set  
            elif self.create_bhive_indexes and template['is_vector'] and template['indexname'].startswith('bhive'):
                self.idx_def_templates.append(template)
        self.log.info(f"Idx definition {self.idx_def_templates}")
        self.log.info(f"Capella flag is set to {self.capella_run}. Use tls flag is set to {self.use_tls}")
        if self.use_https:
            self.log.info("This is Capella run.")
            for i in range(5):
                try:
                    self.cluster = Cluster('couchbases://' + self.node_addr + '?ssl=no_verify',
                                           ClusterOptions(PasswordAuthenticator(self.username, self.password)))
                    break
                except:
                    sleep(10)
        else:
            self.log.info(f"This is a Server run. Will create cluster object against server {self.node_addr} "
                          f"with username {self.username} password {self.password}")
            self.cluster = Cluster('couchbase://{0}'.format(self.node_addr),
                                   ClusterOptions(PasswordAuthenticator(self.username, self.password)))
        if self.bucket_name is not None:
            self.cb = self.cluster.bucket(self.bucket_name)
            self.coll_manager = self.cb.collections()
        else:
            self.log.error("No bucket name has been passed. So no couchbase bucket object will be created")
        if args.bucket_list:
            self.bucket_list = args.bucket_list.split(",")
        else:
            try:
                self.bucket_list = self.get_all_buckets()
            except:
                self.log.error("Fetching buckets query has failed. create_n_indexes_on_bucket will not work")
        self.index_nodes = self.find_nodes_with_service(self.get_services_map(), "index")
        self.n1ql_nodes = self.find_nodes_with_service(self.get_services_map(), "n1ql")
        self.log.info(f"N1QL nodes {self.n1ql_nodes} and Index nodes : {self.index_nodes}")
        # Set max number of replica for the test. For that, fetch the number of indexer nodes in the cluster.
        self.max_num_replica = 0
        self.max_num_partitions = 64
        ## TODO What should be done with this?
        # self.set_max_num_replica()

        # Node SSH default credentials
        self.ssh_username = "root"
        self.ssh_password = "couchbase"

    """
    Create scope and collections in the cluster for the given bucket when the test mode is on.
    """

    def create_scopes_collections(self):
        for i in range(0, TOTAL_SCOPES):
            scopename = self.bucket_name + SCOPENAME_SUFFIX + str(i + 1)
            try:
                self.log.info("creating scope: {}".format(scopename))
                self.coll_manager.create_scope(scopename)
            except ScopeAlreadyExistsException:
                self.log.error("scope: {} already exists. So not creating it again".format(scopename))
            for j in range(0, TOTAL_COLL_PER_SCOPE):
                collectionname = scopename + "_coll" + str(j + 1)
                self.log.info("creating collection: {}".format(collectionname))
                coll_spec = CollectionSpec(collectionname, scopename)
                self.coll_manager.create_collection(coll_spec)

    def fetch_rest_url(self, url):
        """
        meant to find the srv record for Capella runs
        """
        self.log.info("This is a Capella run. Finding the srv domain for {}".format(url))
        srv_info = {}
        srv_records = dns.resolver.resolve('_couchbases._tcp.' + url, 'SRV')
        for srv in srv_records:
            srv_info['host'] = str(srv.target).rstrip('.')
            srv_info['port'] = srv.port
        self.log.info("This is a Capella run. Srv info {}".format(srv_info))
        return srv_info['host']

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
        self.log.info(
            f"Starting to create indexes. Will create {max_num_idx} indexes on these collections {keyspace_name_list}")
        reference_index_map = NestedDict()
        keyspaceused = []
        create_queries_with_node_clause = []
        while total_idx_created < max_num_idx:
            for keyspace_name in keyspace_name_list:
                bucket, scope, collection = keyspace_name.split('.')
                keyspaceused.append(keyspace_name)

                # Choose upto 3 random template definitions to create indexes with
                idx_def_templates = random.sample(self.idx_def_templates, 3)
                self.log.info(f"Index chosen randomly from the templates:{idx_def_templates}")
                for idx_template in idx_def_templates:
                    idx_statement = idx_template['statement']
                    if self.user_specified_prefix:
                        idx_prefix = self.user_specified_prefix + ''.join(
                            random.choices(string.ascii_letters + string.digits, k=random.randint(4, 8)))
                    else:
                        idx_prefix = ''.join(
                            random.choices(string.ascii_letters + string.digits, k=random.randint(4, 8)))
                    idx_name = f"{idx_template['indexname']}_{idx_prefix}"

                    is_partitioned_idx = bool(random.getrandbits(1))
                    is_defer_idx = bool(random.getrandbits(1))
                    idx_instances = 1
                    num_idx = 1
                    with_clause_list = []
                    idx_statement = idx_statement.replace("keyspacenameplaceholder", keyspace_name)
                    idx_statement = idx_statement.replace('idxprefix', idx_prefix)
                    keyspace_name = keyspace_name.replace("`", "")
                    reference_index_map[keyspace_name][idx_name]['bucket'] = bucket.replace("`", "")
                    reference_index_map[keyspace_name][idx_name]['scope'] = scope.replace("`", "")
                    reference_index_map[keyspace_name][idx_name]['collection'] = collection.replace("`", "")
                    reference_index_map[keyspace_name][idx_name]['defer'] = is_defer_idx
                    reference_index_map[keyspace_name][idx_name]['partition'] = is_partitioned_idx
                    if self.install_mode == "ee" and is_partitioned_idx and (not self.disable_partitioned_indexes):
                        idx_statement = idx_statement + " partition by hash(meta().id) "
                        if self.capella_run:
                            ## TODO How do we set this? Is it always 8?
                            reference_index_map[keyspace_name][idx_name]['num_partition'] = 8
                        else:
                            num_partition = random.randint(2, self.max_num_partitions + 1)
                            with_clause_list.append("\'num_partition\':%s" % num_partition)
                            idx_instances *= num_partition
                            reference_index_map[keyspace_name][idx_name]['num_partition'] = num_partition
                    else:
                        reference_index_map[keyspace_name][idx_name]['num_partition'] = 1
                    if self.capella_run:
                        ## TODO How do we set replica counts on capella? Is it always 1?
                        reference_index_map[keyspace_name][idx_name]['replica_count'] = 2
                    elif self.install_mode == "ee" and self.max_num_replica > 0:
                        num_replica = random.randint(1, self.max_num_replica)
                        with_clause_list.append("\'num_replica\':%s" % num_replica)
                        idx_instances *= num_replica + 1
                        reference_index_map[keyspace_name][idx_name]['replica_count'] = num_replica + 1
                        if random.choice([True, False]):
                            index_nodes = self.get_indexer_nodes()
                            nodes_list = random.sample(index_nodes, num_replica + 1)

                            deploy_nodes = ",".join([f"\'{node}:{self.port}\'" for node in nodes_list])

                            with_clause_list.append("\'nodes\': [%s]" % deploy_nodes)

                    if is_defer_idx:
                        with_clause_list.append("\'defer_build\':true")

                    if (is_partitioned_idx and not self.disable_partitioned_indexes) or (
                            self.max_num_replica > 0) or is_defer_idx:
                        idx_statement = idx_statement + " with {"
                        idx_statement = idx_statement + ','.join(with_clause_list) + "}"
                    if "nodes" in idx_statement:
                        create_queries_with_node_clause.append(idx_statement)
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
        self.log.debug("create_index_statements ", create_index_statements)

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
            self.log.info(f"Index map obtained from the rest call : {index_map_from_system_indexes}")
            for keyspace_name in list(reference_index_map):
                ref_keyspace_dict = reference_index_map[keyspace_name.replace("`", "")]
                actual_keyspace_dict = index_map_from_system_indexes[keyspace_name.replace("`", "")]
                self.log.info(f"Will compare {ref_keyspace_dict} against {actual_keyspace_dict}")
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
                    self.log.error(f"Replica count is not matching with expected value. for {index['name']}."
                                   f"Actual: {index['numReplica'] + 1},"
                                   f" Expected: {reference_index_map[keyspace_name][index_name]['replica_count']}")
                if reference_index_map[keyspace_name][index_name]['num_partition'] != index['numPartition']:
                    self.log.error(f"Index Partition no. is not matching with expected value for {index['name']}."
                                   f"Actual: {index['numPartition']},"
                                   f" Expected: {reference_index_map[keyspace_name][index_name]['numPartition']}")
                if reference_index_map[keyspace_name][index_name]['defer']:
                    if index['status'] != 'Created':
                        self.log.error(f"Index status for {index['name']} is not matching with expected value"
                                       f"Expected: Created, Actual: {index['status']}")
                else:
                    if index['status'] != 'Ready':
                        self.log.error(f"Index status for {index['name']} is not matching with expected value"
                                       f"Expected: Created, Actual: {index['status']}")
            if len(create_queries_with_node_clause) > 0:
                self.validate_node_placement_with_nodes_clause(create_queries=create_queries_with_node_clause)

            self.log.info("Validation completed")

    def validate_node_placement_with_nodes_clause(self, create_queries):
        indexer_metadata = self.get_indexer_metadata()['status']

        index_map = {}
        for index_query in create_queries:
            self.log.info(f"index_query is {index_query}")
            out = re.search(self.create_query_node_pattern, index_query, re.IGNORECASE)

            index_name, nodes = out.groups()
            nodes = [node.strip("' ") for node in nodes.split(',')]
            index_map[index_name.strip('`')] = nodes

        for idx in indexer_metadata:
            if idx['scope'] == '_system':
                continue
            idx_name = idx["indexName"]
            if idx_name not in index_map:
                continue
            host = idx['hosts'][0]
            if host not in index_map[idx_name]:
                self.log.error(f"index {idx_name} not present on host {host}")

    def create_n_indexes_on_buckets(self):
        num_of_indexes_per_bucket = self.num_of_indexes_per_bucket
        limit_total_index_count_in_cluster = self.limit_total_index_count_in_cluster
        creation_errors = []  # New list to track all errors

        self.log.info(
            f"Configuration used: Bucket_list {self.bucket_list}. Num of indexes per bucket {num_of_indexes_per_bucket}")
        self.log.info(f"Skip default collection flag {self.skip_default_collection}")
        
        for bucket_name in self.bucket_list:
            if self.use_custom_keyspace:
                keyspaces = [bucket_name + "." + self.use_custom_keyspace]
            else:
                keyspaces = []
                if not self.skip_default_collection:
                    keyspaces.append(f"`{bucket_name}`._default._default")
                bucket_obj = self.cluster.bucket(bucket_name)
                scopes = bucket_obj.collections().get_all_scopes()
                self.log.info("Bucket name {}".format(bucket_name))
                for scope in scopes:
                    self.log.info(f"scope is {scope.name}")
                    if "scope_" in scope.name:
                        for coll in scope.collections:
                            self.log.info(f"coll is {coll.name}")
                            if "coll_" in coll.name:
                                keyspaces.append("`" + bucket_name + "`.`" + scope.name + "`.`" + coll.name + "`")
            self.log.info("Keyspaces that will be used: {}".format(keyspaces))
            total_idx_created = 0
            self.log.info(f"Starting to create indexes. Will create a total of {num_of_indexes_per_bucket} indexes on these collections {keyspace_name_list}")
            keyspace_list = []
            
            while total_idx_created < num_of_indexes_per_bucket:
                create_index_statements = []
                keyspace = random.choice(list(set(keyspaces) - set(keyspace_list)))
                keyspace_list.append(keyspace)
                total_index_count_in_cluster = self.fetch_total_index_count_in_the_cluster()
                
                if total_index_count_in_cluster >= limit_total_index_count_in_cluster:
                    break

                for idx_template in self.idx_def_templates:
                    self.log.info(f"idx_template is {idx_template}")
                    idx_statement = idx_template['statement']
                    if self.user_specified_prefix:
                        idx_prefix = self.user_specified_prefix + ''.join(
                            random.choices(string.ascii_letters + string.digits, k=random.randint(4, 8)))
                    else:
                        idx_prefix = ''.join(
                            random.choices(string.ascii_letters + string.digits, k=random.randint(4, 8)))
                    # create partitioned indexes for all array indexes on Capella clusters.
                    # For the rest, it's randomised
                    if self.capella_run or self.use_tls:
                        if idx_template['indexname'] in ["idx3", "idx4", "idx6", "idx7", "idx12", "idx13"]:
                            is_partitioned_idx = bool(random.getrandbits(1))
                        else:
                            is_partitioned_idx = False
                    else:
                        if idx_template['indexname'] in ['bhiveidxvector3', "idxvector7"]:
                            is_partitioned_idx = False
                        else:
                            is_partitioned_idx = bool(random.getrandbits(1))
                    is_defer_idx = bool(random.getrandbits(1)) or self.defer_build
                    with_clause_list = []
                    idx_statement = idx_statement.replace("keyspacenameplaceholder", keyspace)
                    idx_statement = idx_statement.replace('idxprefix', idx_prefix)
                    if self.xattrs:
                        idx_statement = idx_statement.replace("vectors", "META().xattrs.vectors ")
                    if self.base64_encoding:
                        idx_statement = idx_statement.replace("vectors", "DECODE_VECTOR(vectors, false) ")
                    if self.install_mode == "ee":
                        if is_partitioned_idx:
                            idx_statement = idx_statement + " partition by hash(meta().id) "
                        if self.capella_run and is_partitioned_idx:
                            with_clause_list.append("\'num_partition\':8")
                        else:
                            if is_partitioned_idx:
                                num_partition = random.randint(2, 64)
                                with_clause_list.append("\'num_partition\':%s" % num_partition)
                    if self.install_mode == "ee" and self.max_num_replica > 0:
                        num_replica = random.randint(1, self.max_num_replica)
                        with_clause_list.append("\'num_replica\':%s" % num_replica)
                    if is_defer_idx:
                        with_clause_list.append("\'defer_build\':true")
                    is_vector = self.create_vector_indexes or self.create_bhive_indexes
                    if is_vector and "is_vector" in idx_template and \
                            idx_template['is_vector']:
                        self.log.info("Creating vector index definitions")
                        if self.use_description:
                            description = self.use_description
                        else:
                            description = random.choice(DESCRIPTION_LIST)
                        if self.distance_algo:
                            similarity = self.distance_algo
                        else:
                            similarity = random.choice(DISTANCE_SUPPORTED_FUNCTIONS)
                        self.num_dimensions = int(self.num_dimensions)
                        use_custom_nprobes = bool(random.getrandbits(1))
                        # Set persist_full_vector to true 25% of the time
                        use_custom_persist_full_vector = random.random() < 0.25
                        # commented until a decision is made on the custom trainlist number
                        # use_custom_trainlist = bool(random.getrandbits(1))
                        use_custom_trainlist = False
                        with_clause_list.append(f"\"dimension\":{self.num_dimensions}, "
                                                f"\"description\": \"{description}\","
                                                f"\"similarity\":\"{similarity}\"")
                        # Only set persist_full_vector for BHIVE indexes
                        if self.create_bhive_indexes and use_custom_persist_full_vector:
                            with_clause_list.append(f"\"persist_full_vector\":\"true\"")
                        if use_custom_nprobes:
                            custom_nprobe = random.randint(SCAN_NPROBE_MIN, SCAN_NPROBE_MAX)
                            with_clause_list.append(f"\"scan_nprobes\":{custom_nprobe}")
                        if use_custom_trainlist:
                            sqrt_val = math.floor(math.sqrt(self.num_vectors))
                            # default is 5 times the num of centroids
                            custom_trainlist = random.randint(sqrt_val * 8, sqrt_val * 10)
                            with_clause_list.append(f"\"train_list\":{custom_trainlist}")
                    if (is_partitioned_idx and not self.disable_partitioned_indexes) or (
                            self.max_num_replica > 0) or is_defer_idx:
                        idx_statement = idx_statement + " with {"
                        idx_statement = idx_statement + ','.join(with_clause_list) + "}"
                        create_index_statements.append(idx_statement)
                self.log.info("Create index statements: {}".format(create_index_statements))
                for num, create_index_statement in enumerate(create_index_statements):
                    self.log.info(f"Creating index number {num + 1} on bucket {bucket_name}. "
                                  f"Index statement: {create_index_statement}")
                    try:
                        self._execute_query(create_index_statement)
                        total_idx_created += 1
                        sleep(10)
                    except Exception as err:
                        error_obj = {
                            "bucket": bucket_name,
                            "statement": create_index_statement,
                            "error": str(err)
                        }
                        creation_errors.append(error_obj)
                        self.log.error(f"Index creation failed for statement: {create_index_statement}")
                        self.log.error(err)
                        if "Planner not able to find any node" in str(err):
                            break

                    if total_idx_created == num_of_indexes_per_bucket:
                        break

                # if all the keyspaces are covered and equivalent indexes are not allowed then break the code
                if not list(set(keyspaces) - set(keyspace_list)):
                    if self.allow_equivalent_indexes:
                        keyspace_list = []
                    else:
                        break

        # After all index creation attempts, raise exception if there were errors
        if creation_errors:
            error_message = "The following errors occurred during index creation:\n"
            for error in creation_errors:
                error_message += f"\nBucket: {error['bucket']}\n"
                error_message += f"Statement: {error['statement']}\n"
                error_message += f"Error: {error['error']}\n"
                error_message += "-" * 80
            raise Exception(error_message)

    def random_index_lifecycle_operations(self):
        # Shared dictionary to track created indexes
        created_indexes = {}
        created_indexes_lock = threading.Lock()   
        # Track end time if timeout specified
        end_time = None
        if self.timeout > 0:
            end_time = time.time() + self.timeout

        def random_sleep(min_seconds=30, max_seconds=600):
            sleep_time = random.randint(min_seconds, max_seconds)
            self.log.info(f"Sleeping for {sleep_time} seconds")
            time.sleep(sleep_time)

        def check_timeout():
            if end_time and time.time() > end_time:
                self.log.info(f"Timeout of {self.timeout} seconds reached")
                return True
            return False

        def drop_random_index():
            while not check_timeout():
                try:
                    with created_indexes_lock:
                        self.log.info("Lock acquired by drop_random_index thread")
                        if not created_indexes:
                            continue
                        keyspace = random.choice(list(created_indexes.keys()))
                        if not created_indexes[keyspace]:
                            continue
                        index_name = random.choice(created_indexes[keyspace])
                        self.log.info(f"Dropping random index {index_name} on keyspace {keyspace}")
                        created_indexes[keyspace].remove(index_name)
                        if not created_indexes[keyspace]:
                            del created_indexes[keyspace]
                    self.log.info("Lock released by drop_random_index thread")
                    drop_query = f"DROP INDEX `{index_name}` on {keyspace};"
                    self.log.info(f"Dropping index with statement: {drop_query}")
                    self._execute_query(drop_query)
                    random_sleep(180, 420)
                except Exception as e:
                    self.log.error(f"Error in drop_random_index thread: {str(e)}")
                    time.sleep(60)
                finally:
                    self.log.info("Finally block in drop_random_index executed")
                    time.sleep(30)  

        def create_random_index():
            while not check_timeout():
                try:
                    create_index_statements = self.get_random_create_index_statements()
                    idx_prefix = ''.join(
                            random.choices(string.ascii_letters + string.digits, k=random.randint(4, 8)))
                    random_statement = random.choice(create_index_statements)
                    random_statement = random_statement.replace('idxprefix', idx_prefix)
                    self.log.info(f"Creating random index with statement: {random_statement}")
                    # Extract keyspace and index name from statement before executing
                    match = re.search(r"CREATE\s+(?:VECTOR\s+)?INDEX\s+`?([^`\s]+)`?\s+ON\s+(?:`([^`]+)`|([^`\s]+))(?:\.`?([^`\s]+)`?\.`?([^`\s]+)`?|\._default\._default)", random_statement, re.IGNORECASE)
                    if match:
                        index_name = match.group(1)
                        # Handle both quoted and unquoted bucket names
                        bucket = match.group(2) or match.group(3)
                        if match.group(4) and match.group(5):
                            # Custom scope and collection
                            keyspace = f"`{bucket}`.`{match.group(4)}`.`{match.group(5)}`"
                        else:
                            # Default scope and collection
                            keyspace = f"`{bucket}`._default._default"
                        # Clean up any malformed keyspace names by removing any extra backticks
                        keyspace = re.sub(r'`+', '`', keyspace)
                        if not keyspace.startswith('`'):
                            keyspace = f'`{keyspace}'
                        if not keyspace.endswith('`'):
                            keyspace = f'{keyspace}`'
                        # Execute the create index statement
                        status, results, _ = self._execute_query(random_statement)
                        self.log.info(f"Status: {status}")
                        self.log.info(f"Results: {results}")
                        # Only track the index if creation was successful
                        if status is not None:
                            with created_indexes_lock:
                                self.log.info("Lock acquired by create_random_index thread")
                                if keyspace not in created_indexes:
                                    created_indexes[keyspace] = []
                                created_indexes[keyspace].append(index_name)
                            self.log.info(f"Successfully created and tracked index {index_name} on keyspace {keyspace}")
                            self.log.info(f"Current created_indexes state: {created_indexes}")
                            self.log.info("Lock released by create_random_index thread")
                    else:
                        self.log.error(f"Could not parse index name and keyspace from statement: {random_statement}")
                    random_sleep(60, 120)
                except Exception as e:
                    self.log.error(f"Error in create_random_index thread: {str(e)}")
                    time.sleep(60)

        def alter_random_index():
            while not check_timeout():
                try:
                    with created_indexes_lock:
                        if not created_indexes:
                            continue
                        keyspace = random.choice(list(created_indexes.keys()))
                        if not created_indexes[keyspace]:
                            continue
                        index_name = random.choice(created_indexes[keyspace])
                    time.sleep(60)
                    # Get index details for the selected index
                    idx_node_list = self.find_nodes_with_service(self.get_services_map(), "index")
                    self.log.info(f"keyspace is {keyspace}. idx_node chosen is {idx_node_list[0]}")
                    idx_node_list.sort()
                    keyspace = keyspace.replace('`', '')
                    index_map = self.get_index_map(keyspace.split('.')[0], idx_node_list[0])
                    # Find the selected index in the map
                    index = None
                    self.log.info(f"Index map is {index_map}")
                    for idx in index_map:
                        if idx["indexName"] == index_name:
                            index = idx
                            break
                    if not index:
                        continue
                    self.log.info(f"Index is {index}")
                    # Randomly choose an index to be altered
                    index = random.choice(index_map)
                    self.log.info(f"Index is {index}")
                    # Check the index for replicas
                    idx_replica_count = index["numReplica"]
                    self.log.info(f"Index replica count is {idx_replica_count}")
                    # Perform random alter operation
                    full_keyspace_name = "`" + index["bucket"] + "`.`" + index["scope"] + "`.`" + index["collection"] + "`"
                    full_index_name = "default:" + full_keyspace_name + "." + index["indexName"]
                    possible_actions = []
                    if idx_replica_count > 0:
                        if idx_replica_count == self.max_num_replica:
                            # possible_actions = ["move", "decrease_replica_count", "drop_replica"]
                            possible_actions = [ "decrease_replica_count", "drop_replica"]
                        else:
                            # possible_actions = ["move", "increase_replica_count", "decrease_replica_count", "drop_replica"]
                            possible_actions = ["increase_replica_count", "decrease_replica_count", "drop_replica"]
                    else:
                        # possible_actions = ["move", "increase_replica_count"]
                        possible_actions = ["increase_replica_count"]

                    alter_action = random.choice(possible_actions)
                    with_clause = {}

                    # Build the alter statement based on the chosen action
                    if alter_action == "move":
                        with_clause["action"] = "move"
                        with_clause["nodes"] = [f"{node}:8091" for node in random.sample(idx_node_list, idx_replica_count + 1)]
                    elif alter_action == "increase_replica_count":
                        with_clause["action"] = "replica_count"
                        with_clause["num_replica"] = idx_replica_count + 1
                    elif alter_action == "decrease_replica_count":
                        with_clause["action"] = "replica_count" 
                        with_clause["num_replica"] = idx_replica_count - 1
                    elif alter_action == "drop_replica":
                        with_clause["action"] = "drop_replica"
                        with_clause["replicaId"] = random.randint(0, idx_replica_count)

                    alter_stmt = f"ALTER INDEX {full_index_name} WITH {str(with_clause)}"
                    self.log.info(f"Altering random index with statement: {alter_stmt}")
                    self._execute_query(alter_stmt)
                    random_sleep(240, 480)
                except Exception as e:
                    self.log.error(f"Error in alter_random_index thread: {str(e)}")
                    time.sleep(60)

        def build_random_index():
            while not check_timeout():
                try:
                    with created_indexes_lock:
                        if not created_indexes:
                            continue
                        keyspace = random.choice(list(created_indexes.keys()))
                    self.log.info("Lock released by build_random_index thread")
                    time.sleep(60)
                    self.log.info(f"Building random index for keyspace {keyspace}")
                    self.build_all_deferred_indexes([keyspace])
                    random_sleep(300, 400)
                except Exception as e:
                    self.log.error(f"Error in build_random_index thread: {str(e)}")
                    time.sleep(60)

        # Start the threads
        threads = []
        thread = threading.Thread(target=create_random_index, name="create_thread", daemon=True)
        threads.append(thread)
        thread.start()
        self.log.info(f"Started create_thread. Will wait 10 minutes before starting other threads")
        time.sleep(600)

        thread_funcs = [
            ("drop_thread", drop_random_index),
            ("build_thread", build_random_index),
            ("alter_thread", alter_random_index)
        ]

        for name, func in thread_funcs:
            thread = threading.Thread(target=func, name=name, daemon=True)
            threads.append(thread)
            thread.start()
            self.log.info(f"Started {name}")

        # Monitor threads and restart if needed
        try:
            while not check_timeout():
                for thread in threads:
                    if not thread.is_alive():
                        self.log.error(f"Thread {thread.name} died, restarting...")
                        new_thread = threading.Thread(
                            target=dict(thread_funcs)[thread.name],
                            name=thread.name,
                            daemon=True
                        )
                        threads.remove(thread)
                        threads.append(new_thread)
                        new_thread.start()
                time.sleep(60)
        except KeyboardInterrupt:
            self.log.info("Stopping random index lifecycle operations")
        except Exception as e:
            self.log.error(f"Error in main thread: {str(e)}")
            raise

    def get_all_keyspaces(self):
        keyspaces = []
        for bucket_name in self.bucket_list:
            if self.use_custom_keyspace:
                keyspaces.append(bucket_name + "." + self.use_custom_keyspace)
            bucket_obj = self.cluster.bucket(bucket_name)
            scopes = bucket_obj.collections().get_all_scopes()
            for scope in scopes:
                self.log.info(f"scope is {scope.name}")
                if "scope_" in scope.name:
                    for coll in scope.collections:
                        self.log.info(f"coll is {coll.name}")
                        if "coll_" in coll.name:
                            keyspaces.append("`" + bucket_name + "`.`" + scope.name + "`.`" + coll.name + "`")
        return keyspaces

    def get_random_create_index_statements(self):
        self.log.info(f"Skip default collection flag {self.skip_default_collection}")
        create_index_statements = []
        for bucket_name in self.bucket_list:
            if self.use_custom_keyspace:
                keyspaces = [bucket_name + "." + self.use_custom_keyspace]
            else:
                keyspaces = []
            if not self.skip_default_collection:
                keyspaces.append(f"`{bucket_name}`._default._default")
            bucket_obj = self.cluster.bucket(bucket_name)
            scopes = bucket_obj.collections().get_all_scopes()
            for scope in scopes:
                self.log.info(f"scope is {scope.name}")
                if "scope_" in scope.name:
                    for coll in scope.collections:
                        self.log.info(f"coll is {coll.name}")
                        if "coll_" in coll.name:
                            keyspaces.append("`" + bucket_name + "`.`" + scope.name + "`.`" + coll.name + "`")
            for keyspace in keyspaces:
                for idx_template in HOTEL_DS_INDEX_TEMPLATES:
                    idx_statement = idx_template['statement']
                # create partitioned indexes for all array indexes on Capella clusters.
                # For the rest, it's randomised
                    if self.capella_run or self.use_tls:
                        if idx_template['indexname'] in ["idx3", "idx4", "idx6", "idx7", "idx12", "idx13"]:
                            is_partitioned_idx = bool(random.getrandbits(1))
                        else:
                            is_partitioned_idx = False
                    else:
                        if idx_template['indexname'] in ['bhiveidxvector3', "idxvector7"]:
                            is_partitioned_idx = False
                        else:
                            is_partitioned_idx = bool(random.getrandbits(1))
                    is_defer_idx = bool(random.getrandbits(1)) or self.defer_build
                    with_clause_list = []
                    idx_statement = idx_statement.replace("keyspacenameplaceholder", keyspace)
                    if is_partitioned_idx:
                        idx_statement = idx_statement + " partition by hash(meta().id) "
                    if self.capella_run and is_partitioned_idx:
                        with_clause_list.append("\'num_partition\':8")
                    else:
                        if is_partitioned_idx:
                            num_partition = random.randint(2, 64)
                            with_clause_list.append("\'num_partition\':%s" % num_partition)
                    num_replica = random.randint(1, self.max_num_replica)
                    with_clause_list.append("\'num_replica\':%s" % num_replica)
                    if is_defer_idx:
                        with_clause_list.append("\'defer_build\':true")
                    if "is_vector" in idx_template and idx_template['is_vector'] and self.create_vector_indexes:
                        create_vector_indexes = True
                    else:
                        create_vector_indexes = False
                    if "is_bhive" in idx_template and idx_template['is_bhive'] and self.create_bhive_indexes:
                        create_bhive_indexes = True
                    else:
                        create_bhive_indexes = False
                    is_vector = create_vector_indexes or create_bhive_indexes
                    if is_vector and "is_vector" in idx_template and \
                            idx_template['is_vector']:
                        if self.use_description:
                            description = self.use_description
                        else:
                            description = random.choice(DESCRIPTION_LIST)
                        if self.distance_algo:
                            similarity = self.distance_algo
                        else:
                            similarity = random.choice(DISTANCE_SUPPORTED_FUNCTIONS)
                        self.num_dimensions = int(self.num_dimensions)
                        use_custom_nprobes = bool(random.getrandbits(1))
                        # Set persist_full_vector to true 25% of the time
                        use_custom_persist_full_vector = random.random() < 0.25
                        # commented until a decision is made on the custom trainlist number
                        # use_custom_trainlist = bool(random.getrandbits(1))
                        use_custom_trainlist = False
                        with_clause_list.append(f"\"dimension\":{self.num_dimensions}, "
                                                f"\"description\": \"{description}\","
                                                f"\"similarity\":\"{similarity}\"")
                        # Only set persist_full_vector for BHIVE indexes
                        if create_bhive_indexes and use_custom_persist_full_vector:
                            with_clause_list.append(f"\"persist_full_vector\":\"false\"")
                        if use_custom_nprobes:
                            custom_nprobe = random.randint(SCAN_NPROBE_MIN, SCAN_NPROBE_MAX)
                            with_clause_list.append(f"\"scan_nprobes\":{custom_nprobe}")
                        if use_custom_trainlist:
                            sqrt_val = math.floor(math.sqrt(self.num_vectors))
                            # default is 5 times the num of centroids
                            custom_trainlist = random.randint(sqrt_val * 8, sqrt_val * 10)
                            with_clause_list.append(f"\"train_list\":{custom_trainlist}")
                    if (is_partitioned_idx and not self.disable_partitioned_indexes) or (
                            self.max_num_replica > 0) or is_defer_idx:
                        idx_statement = idx_statement + " with {"
                        idx_statement = idx_statement + ','.join(with_clause_list) + "}"
                    create_index_statements.append(idx_statement)
        return create_index_statements
    
    def fetch_total_index_count_in_the_cluster(self):
        idx_nodes = self.find_nodes_with_service(self.get_services_map(), "index")
        index_count_total = 0
        for idx_node in idx_nodes:
            endpoint = f"{self.scheme}://{idx_node}:{self.node_port_index}/stats"
            self.log.debug(f"Endpoint used for stats {endpoint}")
            response = requests.get(endpoint, auth=(
                self.username, self.password), verify=False, timeout=300)
            response_temp = json.loads(response.text)
            index_count_node = response_temp['num_indexes']
            self.log.info(f"Index count on - {idx_node} is {index_count_node}")
            index_count_total += index_count_node
        self.log.info(f"Total index count as of now - {index_count_total}")
        return index_count_total

    def print_stats_to_console(self):
        idx_nodes = self.find_nodes_with_service(self.get_services_map(), "index")
        table = BeautifulTable()
        table.column_widths = [40, 20, 20, 20, 20, 20, 20]
        table.maxwidth = 200
        table.wrap_on_max_width = True
        table.column_headers = ["Node", "Num. of Indexes", "Resident Ratio", "Total Data Size (GB)", "Total Disk Size (GB)", "Memory RSS (GB)", "CPU Utilization"]
        for idx_node in idx_nodes:
            endpoint = f"{self.scheme}://{idx_node}:{self.node_port_index}/stats"
            response = requests.get(endpoint, auth=(
                self.username, self.password), verify=False, timeout=300)
            response_temp = json.loads(response.text)
            index_count_node, rr, memory_rss, cpu_utilization = response_temp['num_indexes'], \
                                               response_temp['avg_resident_percent'], \
                                                round(response_temp['memory_rss'] / (1024 * 1024 * 1024), 2), \
                                                response_temp['cpu_utilization']
            total_data_size, total_disk_size = round(response_temp['total_data_size'] / (1024 * 1024 * 1024), 2), \
                                               round(response_temp['total_disk_size'] / (1024 * 1024 * 1024), 2)
            table.append_row([idx_node, index_count_node, rr, total_data_size, total_disk_size, memory_rss, cpu_utilization])
        self.log.info("The stats as of now are as follows:\n" + str(table))

    def monitor_index_health(self):
        """Monitors index health by spawning separate threads for memory monitoring and stats printing.
        If timeout is set, monitors for that duration. Otherwise only does a single stats check."""
        if not self.timeout:
            # Just do a single stats check if no timeout specified
            self.print_stats_to_console()
            return

        self.log.info(f"Starting index health monitoring for {self.timeout} seconds")
        
        # Create and start memory monitoring thread
        print("Starting memory monitoring thread")
        memory_thread = threading.Thread(target=self.monitor_memory_usage, 
                                    name="memory_monitor",
                                    daemon=True)
        memory_thread.start()
        # Create and start stats printing thread
        print("Starting stats printing thread")
        stats_thread = threading.Thread(target=self._print_stats_periodically,
                                    name="stats_printer", 
                                    daemon=True)
        stats_thread.start()
        # Wait until timeout
        end_time = time.time() + self.timeout
        try:
            while time.time() < end_time:
                if not memory_thread.is_alive() or not stats_thread.is_alive():
                    raise Exception("One of the monitoring threads died unexpectedly")
                time.sleep(120)
        except KeyboardInterrupt:
            self.log.info("Monitoring interrupted by user")
        except Exception as e:
            self.log.error(f"Error during monitoring: {str(e)}")
            raise
        finally:
            self.log.info("Index health monitoring completed")

    def _print_stats_periodically(self):
        """Helper method to periodically print stats until timeout."""
        while True:
            self.print_stats_to_console()
            self.log.info(f"Sleeping for {self.interval} seconds before next stats check")
            time.sleep(self.interval)
    
    def monitor_memory_usage(self):
        """
        Monitor memory usage of index nodes in parallel.
        Raises exception if memory_rss exceeds memory_total for 3 consecutive cycles.
        """
        INTERVAL = 180  # 3 minutes in seconds
        CONSECUTIVE_THRESHOLD = 3
        
        def monitor_node(node, violation_counts):
            """Thread function to monitor a single node"""
            end_time = time.time() + self.timeout if self.timeout > 0 else float('inf')
            while time.time() < end_time:
                try:
                    endpoint = f"{self.scheme}://{node}:{self.node_port_index}/stats"
                    response = requests.get(endpoint, auth=(
                        self.username, self.password), verify=False, timeout=300)
                    if response.ok:
                        response_temp = json.loads(response.text)
                        memory_rss = response_temp['memory_rss']
                        memory_total = response_temp['memory_total'] 
                        usage_percent = (memory_rss / memory_total) * 100
                        self.log.debug(f"Node {node} - Memory RSS: {memory_rss/(1024*1024*1024):.2f}GB, "
                                f"Total: {memory_total/(1024*1024*1024):.2f}GB, "
                                f"Usage: {usage_percent:.2f}%")
                        if memory_rss > memory_total:
                            # Calculate memory usage percentage
                            usage_percent = (memory_rss / memory_total) * 100
                            self.log.info(f"Node {node} - Memory RSS: {memory_rss/(1024*1024*1024):.2f}GB, "
                                f"Total: {memory_total/(1024*1024*1024):.2f}GB, "
                                f"Usage: {usage_percent:.2f}%")
                            with violation_counts_lock:
                                violation_counts[node] += 1
                                current_violations = violation_counts[node]
                            self.log.warning(f"Node {node} memory_rss exceeds memory_total - "
                                    f"Violation #{current_violations}")
                            if current_violations >= CONSECUTIVE_THRESHOLD:
                                self.run_memory_profile_collects(node)
                                self.log.info(f"Collected memory profile for node {node}. Will sleep for 5 minutes to let the system recover")
                                time.sleep(300)
                                # Reset violation count after collecting memory profile
                                with violation_counts_lock:
                                    violation_counts[node] = 0
                                    self.log.info(f"Reset violation count for node {node} after collecting memory profile")
                        else:
                            # Reset violation count if memory usage returns to normal
                            with violation_counts_lock:
                                if violation_counts[node] > 0:
                                    self.log.info(f"Node {node} memory usage returned to normal levels")
                                    violation_counts[node] = 0
                except Exception as e:
                    self.log.error(f"Error collecting stats from node {node}: {str(e)}")
                    
                time.sleep(INTERVAL)

        # Get list of index nodes
        idx_nodes = self.get_index_nodes()
        
        # Initialize shared violation counts dict and lock
        violation_counts = {node: 0 for node in idx_nodes}
        violation_counts_lock = threading.Lock()
        self.log.info(f"Monitoring memory usage for nodes {idx_nodes}")
        # Create and start monitoring threads for each node
        monitor_threads = []
        for node in idx_nodes:
            thread = threading.Thread(
                target=monitor_node,
                args=(node, violation_counts),
                name=f"monitor_{node}",
                daemon=True
            )
            monitor_threads.append(thread)
            thread.start()
            
        # Wait for all threads
        try:
            while True:
                all_alive = all(t.is_alive() for t in monitor_threads)
                if not all_alive:
                    raise Exception("One or more monitoring threads died unexpectedly")
                time.sleep(120)
        except KeyboardInterrupt:
            self.log.info("Memory monitoring interrupted by user")
        except Exception as e:
            self.log.error(f"Error during memory monitoring: {str(e)}")
            raise

    def run_memory_profile_collects(self, node):
        url_suffix_list = ["/debug/pprof/profile", "/debug/pprof/heap", "/debug/pprof/goroutine"]
        for url_suffix in url_suffix_list:
            s3_pprof_links_list = []
            url = f'http://{node}:9102{url_suffix}'
            self.log.info(f"Collecting memory profile for node {node}")
            response = requests.get(url, auth=(self.username, self.password))
            node_str = node.replace(".", "_")
            timestamp = datetime.now().strftime("%d_%m_%Y_%H_%M")
            prefix = url_suffix.replace("/debug/pprof/", "")
            s3_file_name = f'{prefix}-{node_str}-{timestamp}'
            # Check if the request was successful
            if response.status_code == 200:
                # Write the response content to a file
                with open(s3_file_name, "wb") as file:
                    file.write(response.content)
                # Upload the file to S3
                public_url = f"https://cb-engineering.s3.amazonaws.com/{s3_file_name}"
                with open(s3_file_name, "rb") as file:
                    response = requests.put(url=public_url, data=file)
                if response.status_code == 200:
                    self.log.info(f"Public URL for the profile files: {public_url}")
                    s3_pprof_links_list.append(public_url)
                else:
                    raise Exception(f"upload failed {response.content}")

            else:
                raise Exception("download failed")
        self.log.info(f"Memory profile links for node {node}: {s3_pprof_links_list}")
        return s3_pprof_links_list
        

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

    def random_recovery(self, timeout=3600, min_frequency=500, max_frequency=900):
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
                    update_stats_query = "UPDATE STATISTICS FOR {0} INDEX ALL WITH {{'update_statistics_timeout': 0}}  ;".format(
                        coll)
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

    def item_count_check(self, sample_size=5, raise_exception=True):
        # Get all index nodes in the cluster
        idx_node_list = self.find_nodes_with_service(self.get_services_map(), "index")
        idx_node_list.sort()
        if self.dataset == "hotel":
            index_definitions = HOTEL_DS_INDEX_TEMPLATES
        else:
            index_definitions = SHOES_INDEX_TEMPLATES
        # Exclude any indexes that have when or where clause in the index definition from item count check
        # as the item count will never match the number of docs in collection because of the partial index.
        # Same goes for array indexes
        ignore_count_index_list = [item['indexname'] for item in index_definitions if
                                   not item['validate_item_count_check']]
        leading_vector_index_list = [item['indexname'] for item in index_definitions if
                                   "vector_leading" in item and item['vector_leading']]
        self.log.info(f"Leading vector index list {leading_vector_index_list}")
        # Get Index Map for indexes in the bucket
        if self.bucket_name:
            bucket_list = [self.bucket_name]
        else:
            bucket_list = self.get_all_buckets()
        errors = []
        for bucket_name in bucket_list:
            index_map = self.get_index_map(bucket_name, idx_node_list[0])
            random.shuffle(index_map)
            self.log.info(f"Item count will be skipped for {ignore_count_index_list}")
            if len(index_map) == 0:
                self.log.info("Item check count not possible, no indexes present for the given bucket.")
                return
            count_check_completed = 0
            for index in index_map:
                idx_prefix = index["name"].split("_")[0]
                if idx_prefix in ignore_count_index_list:
                    continue

                if index["scope"] != "_default" and index["collection"] != "_default":
                    keyspace_path = index["bucket"] + ":" + index["scope"] + ":" + index["collection"] + ":"
                else:
                    keyspace_path = index["bucket"] + ":"
                stat_key = keyspace_path + index["name"] + ":docid_count"
                alt_stat_key = keyspace_path + index["name"] + ":items_count"
                pending_mutations_key = keyspace_path + index["name"] + ":num_docs_pending"
                keyspace_name_for_query = "`" + index["bucket"] + "`.`" + index["scope"] + "`.`" + index[
                    "collection"] + "`"

                index_item_count = 0
                index_pending_mutations = 0
                for host in index["hosts"]:
                    item_count, pending_mutations = self.get_stats(stat_key, alt_stat_key, pending_mutations_key,
                                                                   host.split(":")[0])
                    if item_count >= 0:
                        index_item_count += item_count
                        if not self.all_docs_indexed:
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
                self.log.info(f"Idx prefix is {idx_prefix}")
                if idx_prefix in leading_vector_index_list:
                    kv_item_count_query = "select raw count(*) from {0} where vectors is not null".format(keyspace_name_for_query)
                else:
                    kv_item_count_query = "select raw count(*) from {0}".format(keyspace_name_for_query)
                self.log.info(f"Idx prefix is {idx_prefix}")
                status, results, queryResult = self._execute_query(kv_item_count_query)
                if status is not None:
                    for result in results:
                        self.log.debug(result)
                        kv_item_count = result
                else:
                    self.log.info(
                        "Got an error retrieving stat from query via n1ql with query - {0}. Status : {1} ".format(
                            kv_item_count_query, status))
                    errors_obj = {}
                    errors_obj["type"] = "error_retrieving_stats_from_kv_via_n1ql"
                    errors_obj["index_name"] = index["name"]
                    errors_obj["keyspace"] = keyspace_name_for_query
                    errors.append(errors_obj)

                self.log.info(
                    "Item count for index {0} on {1} is {2}. Total items in collection  {3}".format(
                        index["name"],
                        keyspace_name_for_query,
                        index_item_count,
                        kv_item_count))
                if not self.all_docs_indexed:
                    self.log.info(f"Pending mutations {index_pending_mutations}")
                if int(index_item_count) != int(kv_item_count):
                    errors_obj = {}
                    errors_obj["type"] = "item_count_check_failed"
                    errors_obj["index_name"] = index["name"]
                    errors_obj["keyspace"] = keyspace_name_for_query
                    errors_obj["index_item_count"] = index_item_count
                    errors_obj["index_pending_mutations"] = index_pending_mutations
                    errors_obj["kv_item_count"] = kv_item_count
                    errors.append(errors_obj)
                count_check_completed += 1
                self.log.info(f"count_check_completed = {count_check_completed}")
                if count_check_completed > sample_size:
                    break
        if len(errors) > 0:
            if raise_exception:
                raise Exception("There were errors in the item count check phase - \n{0}".format(errors))
            else:
                return errors
        else:
            self.log.info("Item check count passed. No discrepancies seen.")

    def wait_until_mutations_processed(self):
        # Get all index nodes in the cluster
        idx_node_list = self.find_nodes_with_service(self.get_services_map(), "index")
        end_time = time.time() + self.timeout
        pending_indexes_list = list()
        while time.time() < end_time:
            mutations_pending, pending_indexes_list = False, []
            for idx_node in idx_node_list:
                endpoint = f"{self.scheme}://{idx_node}:{self.node_port_index}/stats"
                for i in range(5):
                    try:
                        response = requests.get(endpoint, auth=(
                            self.username, self.password), verify=False, timeout=300)
                        break
                    except:
                        time.sleep(30)
                if response.ok:
                    response = json.loads(response.text)
                    for key in response.keys():
                        bucket = key.split(":")[0]
                        if bucket in self.bucket_list and "num_docs_pending" in key:
                            if response[key] > 0:
                                mutations_pending = True
                                pending_indexes_list.append(key)
                                break
            if not mutations_pending:
                self.log.info("All the mutations have been processed. Breaking out of the loop")
                break
            time.sleep(300)
        if mutations_pending:
            self.log.error(f"All the mutations have not been processed despite waiting for {self.timeout} seconds."
                           f"Pending indexes list {pending_indexes_list}")
            raise Exception("Mutations pending")

    def backstore_mainstore_check(self):
        # Get all index nodes in the cluster
        idx_node_list = self.find_nodes_with_service(self.get_services_map(), "index")
        idx_node_list.sort()
        index_definitions = self.idx_def_templates
        # Exclude all array indexes
        if self.bucket_name:
            bucket_list = [self.bucket_name]
        else:
            bucket_list = self.get_all_buckets()
        ignore_count_index_list = [item['indexname'] for item in index_definitions if
                                   not item['validate_item_count_check']]
        errors = []
        for node in idx_node_list:
            for bucket in bucket_list:
                self.log.info(f"Checking stats for bucket {bucket}")
                index_map = self.get_storage_stats_map(node, bucket=bucket)
                for index in index_map:
                    self.log.debug(f"checking for index {index}")
                    idx_name = index['name'].split(":")[-1]
                    idx_prefix = idx_name.split("_")[0]
                    if idx_prefix in ignore_count_index_list or "backstore_count" not in index:
                        continue
                    if index["mainstore_count"] != index["backstore_count"]:
                        self.log.info(f"Index map as seen during backstore_mainstore_check is {index}")
                        self.log.error(f"Item count mismatch in backstore and mainstore for {index['name']}")
                        errors_obj = dict()
                        errors_obj["type"] = "mismatch in backstore and mainstore"
                        errors_obj["index_name"] = index["name"]
                        errors_obj["mainstore_count"] = index["mainstore_count"]
                        errors_obj["backstore_count"] = index["backstore_count"]
                        errors.append(errors_obj)
        if len(errors) > 0:
            return errors
        else:
            self.log.info("backstore_mainstore_check passed. No discrepancies seen.")

    def get_stats(self, stat_key, alt_stat_key, pending_mutations_key, index_node_addr):
        endpoint = f"{self.scheme}://{index_node_addr}:{self.node_port_index}/stats"
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

                if need_retry:
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

    def set_max_num_replica(self):
        """
        Determine number of index nodes in the cluster and set max num replica accordingly.
        """
        if self.set_max_replicas:
            self.max_num_replica = self.set_max_replicas
        else:
            nodelist = self.find_nodes_with_service(self.get_services_map(), "index")
            if len(nodelist) > 4:
                self.max_num_replica = 3
            else:
                self.max_num_replica = len(nodelist) - 1  # Max num replica = number of idx nodes in cluster - 1
            self.log.info("Setting Max Replica for this test to : {0}".format(self.max_num_replica))

    def get_index_map(self, bucket, index_node_addr):
        """
         Return the index map for the specified bucket
        """
        endpoint = f"{self.scheme}://" + index_node_addr + ":" + self.node_port_index + "/getIndexStatus"
        # Get map of indexes in the cluster
        self.log.debug(f"URL used for get_index_map is {endpoint}")
        response = requests.get(endpoint, auth=(
            self.username, self.password), verify=True, )
        idx_map = []

        if (response.ok):
            response = json.loads(response.text)
            for index in response["status"]:
                if index["bucket"] == bucket and index['scope'] != "_system":
                    idx_map.append(index)

        return idx_map

    def get_storage_stats_map(self, index_node_addr, bucket=None):
        """
         Return the index map for the specified bucket
        """
        endpoint = f"{self.scheme}://" + index_node_addr + ":" + self.node_port_index + "/stats/storage"
        # Get map of indexes in the cluster
        self.log.info(f"URL used for get_index_map is {endpoint}")
        response = requests.get(endpoint, auth=(
            self.username, self.password), verify=True, )
        idx_map = []
        if response.ok:
            response = json.loads(response.text)
            for index in response:
                if bucket is not None and bucket not in index['Index']:
                    continue
                idx_name = index['Index']
                if "items_count" in index["Stats"]["MainStore"]:
                    mainstore_count = index["Stats"]["MainStore"]["items_count"]
                else:
                    mainstore_count = index["Stats"]["MainStore"]["item_count"]
                idx_map.append({"name": idx_name, "mainstore_count": mainstore_count})
                if "BackStore" in index["Stats"]:
                    if "items_count" in index["Stats"]["BackStore"]:
                        idx_map[-1].update({"backstore_count": index["Stats"]["BackStore"]["items_count"]})
                    else:
                        idx_map[-1].update({"backstore_count": index["Stats"]["BackStore"]["item_count"]})
        return idx_map

    def get_stats_map(self, index_node_addr):
        """
         Return the index map for the specified bucket
        """
        endpoint = f"{self.scheme}://" + index_node_addr + ":" \
                   + self.node_port_index + "/stats?async=false"
        # Get map of indexes in the cluster
        self.log.info(f"URL used for get_index_map is {endpoint}")
        response = requests.get(endpoint, auth=(
            self.username, self.password), verify=True, )
        idx_map = {}
        if response.ok:
            response = json.loads(response.text)
            for stat in response.keys():
                if ":items_count" in stat:
                    if len(stat.split(":")) == 3:
                        stat_list = stat.split(":")
                        bucket, idx_name, items_count_str = stat_list[0], stat_list[1], stat_list[2]
                        stat_temp = f"{bucket}:_default:_default:{idx_name}:{items_count_str}:"
                    else:
                        stat_temp = stat
                    idx_map.update({stat_temp.rstrip(":items_count"): response[stat]})
        return idx_map

    def get_services_map(self):
        """
        Populate the service map for all nodes in the cluster.
        """
        if self.capella_run:
            rest_url = self.fetch_rest_url(self.node_addr)
            url = "{}://".format(self.scheme) + rest_url + ":" + self.port
            cluster_url = url + "/pools/default"
        else:
            cluster_url = self.url + "/pools/default"
        node_map = []

        try:
            # Get map of nodes in the cluster

            response = requests.get(cluster_url, auth=(
                self.username, self.password), verify=False)

            if (response.ok):

                response = json.loads(response.text)
                for node in response["nodes"]:
                    clusternode = {}
                    # Workaround for https://issues.couchbase.com/browse/MB-51119
                    clusternode["hostname"] = node["hostname"].replace(":8091", "")
                    clusternode["services"] = node["services"]
                    mem_used = int(node["memoryTotal"]) - int(node["memoryFree"])
                    clusternode["memUsage"] = round(
                        float(mem_used / float(node["memoryTotal"]) * 100), 2)
                    clusternode["cpuUsage"] = round(
                        node["systemStats"]["cpu_utilization_rate"], 2)
                    clusternode["status"] = node["status"]
                    clusternode["clusterMembership"] = node["clusterMembership"]
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

    def create_udfs(self):
        """
        Create n number of UDF on all scopes of a given bucket
        """
        cb_scopes = self.cb.collections().get_all_scopes()
        scope_name_list = []
        for scope in cb_scopes:
            scope_name_list.append("`" + self.bucket_name + "`.`" + scope.name + "`")
        self.log.info(str(scope_name_list))

        # Create JS function
        self.log.info("Create JS Function")
        query_node = self.find_nodes_with_service(self.get_services_map(), "n1ql")[0]
        api1 = "{}://".format(self.scheme) + query_node + ':{}/functions/v1/libraries/math/functions/add'.format(
            self.node_port_query)
        data1 = {"name": "add", "code": "function add(a, b) { let data = a + b; return data; }"}

        api2 = "{}://".format(self.scheme) + query_node + ':{}/functions/v1/libraries/math/functions/sub'.format(
            self.node_port_query)
        data2 = {"name": "add", "code": "function sub(a, b) { let data = a - b; return data; }"}

        api3 = "{}://".format(self.scheme) + query_node + ':{}/functions/v1/libraries/math/functions/mul'.format(
            self.node_port_query)
        data3 = {"name": "add", "code": "function mul(a, b) { let data = a * b; return data; }"}

        api4 = "{}://".format(self.scheme) + query_node + ':{}/functions/v1/libraries/math/functions/div'.format(
            self.node_port_query)
        data4 = {"name": "add", "code": "function div(a, b) { let data = a / b; return data; }"}

        auth = (self.username, self.password)
        try:
            response = requests.get(url=api1, auth=auth, data=data1, timeout=120, verify=False)
            if response.status_code == 200:
                return response.json()

            response = requests.get(url=api2, auth=auth, data=data2, timeout=120, verify=False)
            if response.status_code == 200:
                return response.json()

            response = requests.get(url=api3, auth=auth, data=data3, timeout=120, verify=False)
            if response.status_code == 200:
                return response.json()

            response = requests.get(url=api4, auth=auth, data=data4, timeout=120, verify=False)
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

    def drop_all_udfs(self):
        """
        Drop all UDFs
        """
        drop_function_gen_template = "select raw 'DROP FUNCTION default:`' || identity.`bucket`|| '`.`' || identity.`scope`|| '`.`' || identity.name || '`' from system:functions;"

        self.log.info("Starting to drop all functions ")

        status, results, queryResult = self._execute_query(drop_function_gen_template)
        if status is not None:
            for result in results:
                drop_status, _, _ = self._execute_query(result)

                # Sleep for 0.25 secs after dropping an index
                sleep(0.25)
        self.log.info("Drop all functions completed")

    def find_nodes_with_service(self, node_map, service):
        """
        From the service map, find all nodes running the specified service and return the node list.
        """
        nodelist = []
        for node in node_map:
            if service == "all":
                nodelist.append(node["hostname"])
            else:
                if service in node["services"]:
                    nodelist.append(node["hostname"])
        return nodelist

    def get_index_nodes(self):
        """
        Get list of index nodes with periodic refresh
        """
        current_time = time.time()
        # Initialize or refresh if 20 minutes have passed
        if not hasattr(self, '_idx_nodes_cache_time') or \
           not hasattr(self, '_idx_nodes_cache') or \
           current_time - self._idx_nodes_cache_time > 1200:  # 1200 seconds = 20 minutes
            self._idx_nodes_cache = self.find_nodes_with_service(self.get_services_map(), "index")
            self._idx_nodes_cache_time = current_time
            self.log.info(f"Refreshed index nodes list: {self._idx_nodes_cache}")
        return self._idx_nodes_cache

    # Not working with collections in Python SDK 3.0.4. To be revisited when implemented

    # def build_all_deferred_indexes_sdk(self, keyspace_name_list):
    #    mgr = BucketManager(self.cb, self.bucket_name)
    #    mgr.build_n1ql_deferred_indexes()

    def build_all_deferred_indexes(self, keyspace_name_list, max_collections_to_build=0):
        """
        Build all deferred indexes for all collections of the specified bucket. For each collection, issue a build index
        query with a subquery that would fetch all deferred indexes for that collection.
        """
        build_index_query_template = "SELECT RAW name FROM system:all_indexes WHERE " \
                                   "`using`='gsi' AND '`' || `bucket_id` || '`.`' || `scope_id` || '`.`' || " \
                                   "`keyspace_id` || '`' = 'keyspacename' AND state = 'deferred'"

        for keyspace in keyspace_name_list:
            # Handle default scope/collection case
            if '._default._default' in keyspace:
                bucket_name = keyspace.split('.')[0].replace('`','')
                keyspace = f"`{bucket_name}`"
            # First check if there are any deferred indexes
            check_query = build_index_query_template.replace("keyspacename", keyspace)
            status, results, _ = self._execute_query(check_query)
            if not results or len(results) == 0:
                self.log.info(f"No deferred indexes found for keyspace: {keyspace}")
                continue
            # Build the indexes if there are deferred ones
            build_index_query = f"BUILD INDEX ON {keyspace} ({results})"
            self.log.info(f"Building indexes for keyspace: {keyspace}")
            self.log.info(f"Query used = {build_index_query}")

            status, results, queryResult = self._execute_query(build_index_query)

        self.log.info("Building all deferred indexes completed ")

    def drop_all_indexes(self, keyspace_name_list, validate=True):
        """
        Drop all indexes in the cluster
        """
        if self.user_specified_prefix:
            drop_idx_query_gen_template = "SELECT RAW 'DROP INDEX `' || name || '` on keyspacename;'  " \
                                          "FROM system:all_indexes WHERE '`' || `bucket_id` || '`.`' || `scope_id` " \
                                          "|| '`.`' || `keyspace_id` || '`' = 'keyspacename' " \
                                          f"and name like '%{self.user_specified_prefix}%';"
        else:
            drop_idx_query_gen_template = "SELECT RAW 'DROP INDEX `' || name || '` on keyspacename;'  " \
                                          "FROM system:all_indexes WHERE '`' || `bucket_id` || '`.`' || `scope_id` " \
                                          "|| '`.`' || `keyspace_id` || '`' = 'keyspacename';"

        self.log.info("Starting to drop all indexes ")
        for keyspace in keyspace_name_list:
            drop_idx_query_gen = drop_idx_query_gen_template.replace("keyspacename", keyspace)
            self.log.info("Will run the query:{}".format(drop_idx_query_gen))
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

    def drop_indexes_in_a_loop(self, timeout, interval):
        """
        Drop random indexes in a loop
        """
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

    def _execute_query(self, statement):
        """
        Method to execute a query statement
        """
        status = None
        results = None
        queryResult = None

        try:
            self.log.debug("Will execute the statement:{}".format(statement))
            if self.timeout:
                timeout = timedelta(minutes=self.timeout)
            else:
                timeout = timedelta(minutes=20)
            queryResult = self.cluster.query(statement, QueryOptions(timeout=timeout))
            try:
                status = queryResult.metadata().status()
                results = queryResult.rows()
            except Exception as e:
                self.log.info("Query didnt return status or results")
                self.log.error(
                    f"Unexpected error during execution of query. Query is {statement}. Exception is {str(e)}", )
                pass

        except couchbase.exceptions.QueryException as qerr:
            self.log.debug("qerr")
            self.log.error(qerr)
            # raise Exception(f"Exception seen while running the query {statement}. Error is {str(qerr)}")
        except couchbase.exceptions.HTTPException as herr:
            self.log.debug("herr")
            self.log.error(herr)
            # raise Exception(f"Exception seen while running the query {statement}. Error is {str(herr)}")
        except couchbase.exceptions.QueryIndexAlreadyExistsException as qiaeerr:
            self.log.debug("qiaeerr")
            self.log.error(qiaeerr)
        except couchbase.exceptions.TimeoutException as terr:
            self.log.debug("terr")
            self.log.error(terr)
            # raise Exception(f"Exception seen while running the query {statement}. Error is {str(terr)}")
        except Exception as e:
            self.log.error(f"Unexpected error : {str(e)}")
            # raise Exception(f"Exception seen while running the query {statement}. Error {str(e)}")
        return status, results, queryResult

    def get_indexer_metadata(self, timeout=120):
        idx_node = self.find_nodes_with_service(self.get_services_map(), "index")[0]
        if self.use_https:
            api = f"{self.scheme}://" + idx_node + ':19102/getIndexStatus'
        else:
            api = f"{self.scheme}://" + idx_node + ':9102/getIndexStatus'
        auth = (self.username, self.password)
        try:
            response = requests.get(url=api, auth=auth, timeout=timeout, verify=False)
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

    def create_n1ql_udf(self):
        try:
            # Create JS Library
            # self.lib_filename = '/n1ql_udf.js'
            with open(self.lib_filename, 'rb') as f:
                data = f.read()
            url = "{}://".format(self.scheme) + self.n1ql_nodes[0] + ":{}/evaluator/v1/libraries/".format(
                self.node_port_query) + self.lib_name

            self.log.info("Javascript filepath is {}".format(self.lib_filename))
            self.log.info("File data: \n {}".format(data))
            self.log.info("url: {}".format(url))
            self.log.info("username: {}".format(self.username))
            self.log.info("password: {}".format(self.password))

            auth = (self.username, self.password)
            response = requests.post(url=url,
                                     data=data,
                                     headers={'Content-Type': 'application/json'}, auth=auth, verify=False)
            if response.status_code != 200:
                self.log.error("Error code : {0}".format(response.status_code))
                self.log.error("Error reason : {0}".format(response.reason))
                self.log.error("Error Text : {0}".format(response.text))

            # Create N1QL Function
            n1ql_function_query_stmt = "CREATE OR REPLACE FUNCTION run_n1ql_query(bucketname) LANGUAGE JAVASCRIPT AS 'run_n1ql_query' AT '{0}';".format(
                self.lib_name)
            self.log.info("Create Function Query : {0}".format(n1ql_function_query_stmt))

            status, results, queryResult = self._execute_query(n1ql_function_query_stmt)
            self.log.info(f"Status is {status} Results are {results} queryResult is {queryResult}")
        except Exception as e:
            self.log.error(str(e))

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

    def get_all_buckets(self):
        query = "Select * from system:buckets"
        status, result, _ = self._execute_query(query)
        bucket_list = []
        for item in result:
            bucket_list.append(item['buckets']['name'])
        return bucket_list

    def get_bucket_index_node_map(self):
        indexer_metadata = self.get_indexer_metadata()
        self.log.debug("Indexer metadata:{}".format(indexer_metadata))
        bucket_indexer_node_map = defaultdict(list)
        for index in indexer_metadata['status']:
            for host in index['hosts']:
                self.log.debug("Index is {}. Host is {}".format(index, host))
                host_ip = host.split(":")[0]
                if host_ip not in bucket_indexer_node_map[index['bucket']]:
                    bucket_indexer_node_map[index['bucket']].append(host_ip)
        return bucket_indexer_node_map

    def validate_tenant_affinity(self):
        bucket_indexer_node_map = self.get_bucket_index_node_map()
        self.log.info("Bucket indexer map is {}".format(bucket_indexer_node_map))
        for bucket in bucket_indexer_node_map:
            self.log.info(
                f"Validating tenant affinity for {bucket}. Indexes for {bucket} are on nodes {bucket_indexer_node_map[bucket]}")
            if len(bucket_indexer_node_map[bucket]) != 2:
                self.log.error(f"Tenant affinity not honoured for bucket {bucket}."
                               f"Index hosts the bucket is on:{bucket_indexer_node_map[bucket]}")
                raise Exception("Tenant affinity check fail")
            else:
                self.log.info(f"Tenant affinity honoured for bucket {bucket}")

    def get_indexer_nodes(self):
        service_map = self.get_services_map()
        self.log.info(f"Services map is {service_map}")
        indexer_nodes_list = []
        for node in service_map:
            if "index" in node['services'] and node['status'] == 'healthy' and node['clusterMembership'] == 'active':
                indexer_nodes_list.append(node['hostname'])
        return indexer_nodes_list

    def set_fast_rebalance_config(self):
        indexer_nodes = self.get_indexer_nodes()
        self.log.info("The indexer nodes are {}".format(indexer_nodes))
        node = indexer_nodes[0]
        fast_rebalance_config = {"indexer.settings.rebalance.blob_storage_bucket": self.s3_bucket,
                                 "indexer.settings.rebalance.blob_storage_prefix": self.storage_prefix,
                                 "indexer.settings.rebalance.blob_storage_scheme": "s3",
                                 "indexer.settings.rebalance.blob_storage_region": self.region}
        self.set_index_settings(setting_json=fast_rebalance_config, node_ip=node)

    def copy_aws_keys(self):
        if not self.aws_access_key_id or not self.aws_secret_access_key or not self.region:
            raise Exception("Please pass aws_access_key_id, aws_secret_access_key, and region "
                            "parameters to copy_aws_keys")
        self.log.info("Will use this bucket {} and this storage prefix {}".format(self.s3_bucket,
                                                                                  self.scheme))
        self.log.info("Will use this access key {} and this secret key {}".format(self.aws_access_key_id,
                                                                          self.aws_secret_access_key))
        for node in self.node_list:
            self.log.info(f"Will ssh into {node} and copy the keys")
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(node, username=self.ssh_username, password=self.ssh_password, timeout=10)
            ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("rm -rf /home/couchbase/.aws/")
            out, err = ssh_stdout.read(), ssh_stderr.read()
            self.log.info("Output for rm -rf command {} error {}".format(out, err))
            ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("mkdir -p /home/couchbase/.aws/")
            out, err = ssh_stdout.read(), ssh_stderr.read()
            self.log.info("Output for mkdir command {} error {}".format(out, err))
            remote_path_aws_cred_file = "/home/couchbase/.aws/credentials"
            remote_path_aws_conf_file = '/home/couchbase/.aws/config'
            aws_cred_file = ('[default]\n'
                             f'aws_access_key_id={self.aws_access_key_id}\n'
                             f'aws_secret_access_key={self.aws_secret_access_key}')
            aws_conf_file = ('[default]\n'
                             f'region={self.region}\n'
                             'output=json')
            ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command(
                "echo '{0}' > {1}".format(aws_cred_file, remote_path_aws_cred_file))
            out, err = ssh_stdout.read(), ssh_stderr.read()
            self.log.info("Output for creating aws cred file command {} error {}".format(out, err))
            ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command(
                "echo '{0}' > {1}".format(aws_conf_file, remote_path_aws_conf_file))
            out, err = ssh_stdout.read(), ssh_stderr.read()
            self.log.info("Output for creating aws conf file command {} error {}".format(out, err))

    def validate_s3_cleanup(self):
        s3 = boto3.client(service_name='s3', region_name=self.region,
                          aws_access_key_id=self.aws_access_key_id,
                          aws_secret_access_key=self.aws_secret_access_key)
        folder_path_expected = [f"{self.storage_prefix}/"]
        self.log.info(f"Expected folder list {folder_path_expected}")
        result = s3.list_objects_v2(Bucket=self.s3_bucket, Delimiter='/*')
        self.log.info(f"Result from the s3 list_objects_v2 API call:{result}")
        if result['KeyCount'] > 1:
            raise Exception(f"S3 cleanup validation failure. Folder list: {result}")

    def cleanup_s3(self):
        s3 = boto3.client(service_name='s3', region_name=self.region,
                          aws_access_key_id=self.aws_access_key_id,
                          aws_secret_access_key=self.aws_secret_access_key)
        response = s3.list_objects_v2(Bucket=self.s3_bucket, Prefix=self.storage_prefix)
        for obj in response['Contents']:
            if obj['Key'] != '{}/'.format(self.storage_prefix):
                self.log.info('Deleting', obj['Key'])
                s3.delete_object(Bucket=self.s3_bucket, Key=obj['Key'])

    def set_index_settings(self, setting_json, node_ip):
        api = f"{self.scheme}://{node_ip}:{self.node_port_index}/settings"
        self.log.info(f"Endpoint to which index settings will be posted {api}")
        response = requests.post(url=api, data=json.dumps(setting_json), timeout=120, auth=(
            self.username, self.password), verify=False)
        response.raise_for_status()

    def get_total_requests_metric(self, node):
        endpoint = f"{self.scheme}://{node}:{self.node_port_index}/stats"
        self.log.info(f"Endpoint used for get_total_requests_metric {endpoint}")
        response = requests.get(endpoint, auth=(
            self.username, self.password), verify=False, timeout=300)
        if response.ok:
            response = json.loads(response.text)
            return response['total_requests']
        self.log.info(f"Error while fetching get_total_requests_metric - {endpoint}")

    def is_rebalance_running(self):
        endpoint = f"{self.url}/pools/default/rebalanceProgress"
        self.log.info(f"Endpoint used for is_rebalance_running {endpoint}")
        response = requests.get(endpoint, auth=(
            self.username, self.password), verify=False, timeout=300)
        if response.ok:
            response = json.loads(response.text)
            rebalance_progress = response['status']
            self.log.info(f"Rebalance_progress {rebalance_progress}")
            if rebalance_progress != 'none':
                return True
            return False
        self.log.info(f"Error while fetching rebalanceProgress - {endpoint}")

    def wait_until_rebalance_cleanup_done(self, timeout=3600):
        nodes_list = self.get_indexer_nodes()
        time_end, all_nodes_cleaned_up = time.time() + timeout, False
        while time.time() < time_end and not all_nodes_cleaned_up:
            nodes_cleaned_up = []
            for node in nodes_list:
                endpoint = f"{self.scheme}://{node}:{self.node_port_index}/rebalanceCleanupStatus"
                self.log.info(f"Endpoint used for is_rebalance_running {endpoint}")
                response = requests.get(endpoint, auth=(
                    self.username, self.password), verify=False, timeout=300)
                if response.ok:
                    status = response.text
                    self.log.info(f"Cleanup status {status}")
                    if status == 'done':
                        nodes_cleaned_up.append(node)
                time.sleep(10)
            if len(nodes_cleaned_up) == len(nodes_list):
                all_nodes_cleaned_up = True
            time.sleep(30)

    def poll_total_requests_during_rebalance(self):
        nodes_list = self.get_indexer_nodes()
        self.log.info(f"List of nodes with index service{nodes_list}")
        if self.sleep_before_polling:
            self.log.info(f"Sleeping for {self.sleep_before_polling} seconds before polling")
            time.sleep(int(self.sleep_before_polling))
        is_rebalance_running = True
        while is_rebalance_running:
            new_nodes = []
            for node in nodes_list:
                try:
                    total_requests = self.get_total_requests_metric(node=node)
                    if total_requests == 0:
                        new_nodes.append(node)
                    self.log.info(f"Total requests param on node {node}: {total_requests}")
                except:
                    pass
            time.sleep(300)
            # this is a hack. Need to switch to use_capella flag once things are stable.
            if self.use_tls:
                if self.get_capella_cluster_status() == 'scaling':
                    is_rebalance_running = True
                else:
                    is_rebalance_running = False
            else:
                is_rebalance_running = self.is_rebalance_running()
        raise Exception("Dummy exception statement. Ignore. Throwing an exception to print docker logs to console.")

    def get_capella_cluster_status(self):
        response = requests.get(
            f"https://api.{self.sbx}/internal/support/clusters/{self.capella_cluster_id}",
            headers={"Authorization": f"Bearer {self.token}"})
        if response.status_code != 200:
            raise Exception("Response when trying to fetch cluster status")
        resp_json = response.json()
        self.log.info(f"Response get_capella_cluster_status {resp_json}")
        cluster_status = resp_json['meta']['status']['state']
        return cluster_status

    def check_item_count_across_replicas(self, sample_size=5):
        idx_node_list = self.find_nodes_with_service(self.get_services_map(), "index")
        idx_maps_dict = dict()
        idx_maps_list = list()
        if self.bucket_name:
            bucket_list = [self.bucket_name]
        else:
            bucket_list = self.get_all_buckets()
        for node in idx_node_list:
            idx_map = self.get_stats_map(node)
            idx_maps_dict[node] = idx_map
            idx_maps_list.append(idx_map)
        partitioned_indexes_list = self.get_partitioned_indexes_list()
        self.log.debug(f"Partitioned indexes {partitioned_indexes_list} ========================")
        errors = []
        random_indexes_to_validate = []
        for node_dict in idx_maps_dict.keys():
            indexes_list_node = idx_maps_dict[node_dict].keys()
            indexes_list_node = list(indexes_list_node)
            random.shuffle(indexes_list_node)
            replicas_only_list = [item for item in indexes_list_node if "replica" in item]
            for bucket in bucket_list:
                replicas_only_list = [item for item in replicas_only_list if bucket in item]
                random_indexes_to_validate += replicas_only_list[:sample_size]
        self.log.info(f"Random indexes to validate: {random_indexes_to_validate}")
        index_map = self.get_indexer_metadata()
        for item in random_indexes_to_validate:
            count_list = []
            if item in partitioned_indexes_list:
                agg_count = self.get_total_item_count_for_partitioned_index(idx_maps_dict, item)
                count_list.append(agg_count)
                self.log.info(f"{item} is a partitioned index. Aggregate count {agg_count}")
                replicas_list = self.find_all_replicas(item, index_map)
                self.log.info(f"Replicas for partitioned index {item} - {replicas_list}")
                for replica in replicas_list:
                    agg_count = self.get_total_item_count_for_partitioned_index(idx_maps_dict, replica)
                    self.log.info(f"Replica index {replica} is a partitioned index. Aggregate count {agg_count}")
                    # TODO: Remove this once the issue is fixed https://jira.issues.couchbase.com/browse/MB-63795
                    if agg_count != 0:
                        count_list.append(agg_count)
            else:
                replicas_list = self.find_all_replicas(item, index_map)
                self.log.info(f"Replicas for index {item} - {replicas_list}")
                count_list = []
                for node_dict in idx_maps_dict.keys():
                    indexes_list_node = idx_maps_dict[node_dict].keys()
                    indexes_list_node = list(indexes_list_node)
                    replica_idx_list = list(set(indexes_list_node).intersection(set(replicas_list)))
                    if replica_idx_list:
                        if len(replica_idx_list) != 1:
                            self.log.error(f"Replicas exist on the same node for {item}")
                        idx_name = replica_idx_list[0]
                        count = idx_maps_dict[node_dict][idx_name]
                        self.log.debug(f"Count is {count}")
                        # TODO: Remove this once the issue is fixed https://jira.issues.couchbase.com/browse/MB-63795
                        if count != 0:
                            count_list.append(count)
            if len(list(set(count_list))) > 1:
                self.log.error(f"Mismatch in item count across replicas for {item}. Count list {count_list}")
                errors_obj = dict()
                errors_obj["index_name"] = item
                errors_obj["index_item_count_list"] = count_list
                errors.append(errors_obj)
        self.log.info("+++++++++++++++++++++END of replica item count check+++++++++++++++++++++++")
        return errors

    def get_total_item_count_for_partitioned_index(self, idx_maps_dict, idx_name):
        agg_count = 0
        for node_dict in idx_maps_dict.keys():
            indexes_list_node = idx_maps_dict[node_dict].keys()
            indexes_list_node = list(indexes_list_node)
            if idx_name in indexes_list_node:
                agg_count += idx_maps_dict[node_dict][idx_name]
        return agg_count

    def get_partitioned_indexes_list(self):
        index_map = self.get_indexer_metadata()
        indexes_dict = index_map['status']
        partitioned_indexes_list = []
        for index in indexes_dict:
            if index["partitioned"]:
                if index['scope'] == '_default':
                    partitioned_indexes_list.append(f"{index['bucket']}:_default:_default:{index['name']}")
                else:
                    partitioned_indexes_list.append(
                        f"{index['bucket']}:{index['scope']}:{index['collection']}:{index['name']}")
        return partitioned_indexes_list


    def get_shards_index_map(self):
        metadata = self.get_indexer_metadata()
        shard_index_map = {}
        for index_metadata in metadata['status']:
            if index_metadata.get('alternateShardIds'):
                for host in index_metadata['alternateShardIds']:
                    for partition in index_metadata['alternateShardIds'][host]:
                        shards = index_metadata['alternateShardIds'][host][partition][0][:-2]
                        full_index_name = f"{index_metadata['bucket']}:{index_metadata['scope']}:{index_metadata['collection']}:{index_metadata['name']}"
                        if shards in shard_index_map:
                            shard_index_map[shards].append(full_index_name)
                        else:
                            shard_index_map[shards] = [full_index_name]

        for key, value in shard_index_map.items():
            shard_index_map[key] = list(set(shard_index_map[key]))
        return shard_index_map

    def get_index_types(self):
        """
        Get lists of indexes categorized by their types by querying the /getIndexStatus endpoint.
        
        Returns:
            tuple: Three lists containing (vector_index_list, bhive_index_list, scalar_index_list)
        """
        vector_index_list = []
        bhive_index_list = []
        scalar_index_list = []
        
        # Get index metadata from indexer node
        index_metadata = self.get_indexer_metadata()
        if not index_metadata or 'status' not in index_metadata:
            self.log.error("Failed to get index metadata")
            return vector_index_list, bhive_index_list, scalar_index_list
            
        for index in index_metadata['status']:
            # Construct the full index name
            if index['scope'] == '_default':
                full_index_name = f"{index['bucket']}:_default:_default:{index['name']}"
            else:
                full_index_name = f"{index['bucket']}:{index['scope']}:{index['collection']}:{index['name']}"
                
            # Check index definition to categorize
            definition = index.get('definition', '').lower()
            
            if "create vector index" in definition:
                bhive_index_list.append(full_index_name)
            elif "vector" in definition in definition and "similarity" in definition and "description" in definition:
                vector_index_list.append(full_index_name)
            else:
                scalar_index_list.append(full_index_name)
        
        self.log.info(f"Vector indexes: {vector_index_list}")
        self.log.info(f"BHIVE indexes: {bhive_index_list}")
        self.log.info(f"Scalar indexes: {scalar_index_list}")
        return vector_index_list, bhive_index_list, scalar_index_list

    def validate_shard_seggregation(self):
        vector_index_list, bhive_index_list, scalar_index_list = self.get_index_types()
        shard_index_map = self.get_shards_index_map()
        self.log.debug(f"Shard index map {shard_index_map}")
        errors = []
        
        for shard, indices in shard_index_map.items():
            categories_found = set()
            for index in indices:
                if index in vector_index_list:
                    categories_found.add('vector')
                elif index in bhive_index_list:
                    categories_found.add('bhive')
                elif index in scalar_index_list:
                    categories_found.add('scalar')
                    
            # Check if more than one category is found for this shard
            if len(categories_found) != 1:
                errors_obj = {
                    "type": "Multiple index categories found in single shard",
                    "shard": shard,
                    "indices": indices,
                    "categories": list(categories_found)
                }
                errors.append(errors_obj)
                self.log.error(f"Shard {shard} contains mixed index types: {categories_found}")
                
        return errors

    def find_all_replicas(self, name, index_map):
        indexes_dict = index_map['status']
        replicas_list = []
        defn_Id = None
        for index in indexes_dict:
            index_list_full = name.split(":")
            if index['name'] == index_list_full[-1] and index['bucket'] == index_list_full[0] \
                    and index['scope'] == index_list_full[1] and index['collection'] == index_list_full[2]:
                defn_Id = index['defnId']
        if not defn_Id:
            raise Exception(f"Could not find defnID for index {name}")
        for index in indexes_dict:
            if index['defnId'] == defn_Id:
                replicas_list.append(f"{index['bucket']}:{index['scope']}:{index['collection']}:{index['name']}")
        return replicas_list

    def post_topology_change_validations(self, sample_size=5):
        errors_item_check = self.item_count_check(sample_size=sample_size, raise_exception=False)
        errors_replica_check = self.check_item_count_across_replicas(sample_size=sample_size)
        errors_backstore_mainstore = self.backstore_mainstore_check()
        errors_shard_seggregation = self.validate_shard_seggregation()
        validations_failed = False
        if errors_item_check:
            self.log.error(f"Item count check failed. Errors {errors_item_check}")
            validations_failed = True
        if errors_replica_check:
            self.log.error(f"Replica item count check failed. Errors {errors_replica_check}")
            validations_failed = True
        if errors_backstore_mainstore:
            self.log.error(f"Backstore mainstore count check failed. Errors {errors_item_check}")
            validations_failed = True
        if errors_shard_seggregation:
            self.log.error(f"Shard seggregation check failed. Errors {errors_shard_seggregation}")
            validations_failed = True
        if validations_failed:
            raise Exception("Post topology validations failed")


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
    indexMgr.set_max_num_replica()
    if indexMgr.test_mode:
        indexMgr.create_scopes_collections()
    sleep(10)

    # Get list of all collections for the bucket
    try:
        keyspace_name_list = indexMgr.get_all_collections()
    except:
        print("No buckets passed. Will not fetch list of collections")
        keyspace_name_list = []

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
    elif indexMgr.action == "post_topology_change_validations":
        indexMgr.post_topology_change_validations(indexMgr.sample_size)
    elif indexMgr.action == "replica_count_check":
        indexMgr.check_item_count_across_replicas()
    elif indexMgr.action == "random_recovery":
        indexMgr.random_recovery(indexMgr.timeout, indexMgr.interval)
    elif indexMgr.action == "create_udf":
        indexMgr.create_udfs()
    elif indexMgr.action == "drop_udf":
        indexMgr.drop_all_udfs()
    elif indexMgr.action == "create_n1ql_udf":
        indexMgr.create_n1ql_udf()
    elif indexMgr.action == "validate_tenant_affinity":
        indexMgr.validate_tenant_affinity()
    elif indexMgr.action == "set_fast_rebalance_config":
        indexMgr.set_fast_rebalance_config()
    elif indexMgr.action == "copy_aws_keys":
        indexMgr.copy_aws_keys()
    elif indexMgr.action == "create_n_indexes_on_buckets":
        indexMgr.create_n_indexes_on_buckets()
    elif indexMgr.action == "validate_s3_cleanup":
        indexMgr.validate_s3_cleanup()
    elif indexMgr.action == "cleanup_s3":
        indexMgr.cleanup_s3()
    elif indexMgr.action == "poll_total_requests_during_rebalance":
        indexMgr.poll_total_requests_during_rebalance()
    elif indexMgr.action == 'wait_until_rebalance_cleanup_done':
        indexMgr.wait_until_rebalance_cleanup_done()
    elif indexMgr.action == 'print_stats':
        indexMgr.monitor_index_health()
    elif indexMgr.action == 'wait_until_mutations_processed':
        indexMgr.wait_until_mutations_processed()
    elif indexMgr.action == 'random_index_lifecycle':
        indexMgr.random_index_lifecycle_operations()
    else:
        print("Invalid choice for action. Choose from the following - "
              "create_index | build_deferred_index | drop_all_indexes | create_index_loop | alter_indexes | "
              "enable_cbo | drop_index_loop | item_count_check | random_recovery | post_topology_change_validations"
              "| create_udf | drop_udf | create_n1ql_udf | validate_tenant_affinity | set_fast_rebalance_config | "
              "validate_s3_cleanup | cleanup_s3 | replica_count_check | wait_until_mutations_processed | random_index_lifecycle")

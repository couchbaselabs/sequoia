"""
TO-DO :
1. Add full encryption remote link support
2. Add external links and external datasets support
"""
import random
import logging
import time
import httplib2
import json
import urllib
from optparse import OptionParser
from datetime import datetime
import copy

##Templates for data-set specific index statements

# Hotel DS
CATAPULT_INDEX_TEMPLATES = [
    "(`type`:string, `price`:bigint)",
    "(`avg_rating`:bigint, `free_breakfast`:string)",
    "(`free_breakfast`:string, `free_parking`:string)",
    "(`country`:string, `price`:bigint)",
    "(`type`:string, `free_breakfast`:string, `free_parking`:string)"
]
GIDEON_INDEX_TEMPLATES = [
    "(`profile`.`likes`:bigint, `rating`:double)",
    "(`totalCount`:bigint, `failCount`:bigint)",
    "(`duration`:bigint)",
    "(`rating`:double, `city`:string, `build`:bigint)"
]

CATAPULT_WHERE_CLAUSE_TEMPLATES = [
    "`type` in [\"Inn\", \"Motels\", \"Suites\"] and price between 300 and 1000",
    "avg_rating > 3.5 and free_breakfast = False",
    "free_breakfast = True or free_parking = True",
    "country like \"S%\" and price < 1500",
    "`type`=\"Hotel\" and free_breakfast = True and free_parking = True"
]
GIDEON_WHERE_CLAUSE_TEMPLATES = [
    "rating > 50 and profile.likes > 3000 or len(profile.friends) > 3",
    "rating > 67 and city like \"G%\" or city like \"M%\" and build > 100",
    "failCount between 0 and 10 or totalCount > 10",
    "duration > 500"
]

DATAVERSE_PREFIX_1 = "dv_{0}"
DATAVERSE_PREFIX_2 = "dv_{0}.dv_{0}"
DATASET_PREFIX = "ds_{0}"
INDEX_PREFIX = "idx_{0}"
REMOTE_LINK_PREFIX = "link_{0}"
SYNONYM_PREFIX = "synonym_{0}"

DATAVERSE_MAX_COUNTER = 0
DATASET_MAX_COUNTER = 0
INDEX_MAX_COUNTER = 0
SYNONYM_MAX_COUNTER = 0
LINK_MAX_COUNTER = 0

class AnalyticsOperations():

    def run(self):
        usage = '''%prog -i hostname -u username -p password -b bucket -o operations --dataverse_count --dataset_count 
        --wait_for_ingestion '''
        parser = OptionParser(usage)
        # Required script parameter
        parser.add_option("-i", dest="host", help="server ip without port <ip>")
        parser.add_option("-b", dest="buckets",
                          help="name of the buckets(seperated by comma) to be considered for creating dataset")
        parser.add_option("-o", dest="operations",
                          choices=['create_cbas_infra', 'drop_cbas_infra', 'recreate_cbas_infra',
                                   'create_drop_dataverse_dataset_in_loop'],
                          help="create or delete dataverse/dataset in a loop")

        # Optional script parameter
        parser.add_option("-u", dest="username", default="Administrator", help="user name default=Administrator")
        parser.add_option("-p", dest="password", default="password", help="password default=password")

        # Required if only KV scopes or collections specified are to be considered during dataset creation
        parser.add_option("--inc_scp", dest="include_scopes", default="",
                          help="name of the scopes(seperated by comma) to be considered for creating dataset, "
                               "default is empty string")
        parser.add_option("--inc_coll", dest="include_collections", default="",
                          help="name of the collections(seperated by comma) to be considered for creating dataset, "
                               "default is empty string")
        parser.add_option("--exc_scp", dest="exclude_scopes", default="",
                          help="name of the scopes(seperated by comma) not to be considered for creating dataset, "
                               "default is empty string")
        parser.add_option("--exc_coll", dest="exclude_collections", default="",
                          help="name of the collections(seperated by comma) to be considered for creating dataset, "
                               "default is empty string")

        # Required if operation type is 'create_cbas_infra'
        parser.add_option("--dv_cnt", dest="dataverse_count", type="int", default=1,
                          help="no of dataverses to be created, if count is 1 then no dataverse "
                               "will be created and Default dataverse will be used")
        parser.add_option("--replica_cnt", dest="replica_count", type="int", default=0,
                          help="replica will be created, if count 0 then no replication"
                               "will be created and Default replication will be used")
        parser.add_option("--ds_cnt", dest="dataset_count", type="int", default=1,
                          help="no of dataset to be created, default=1")
        parser.add_option("--ds_dist", dest="dataset_distribution", choices=["uniform", "random"],
                          default="uniform", help="Number of datasets per dataverse to be created uniformly/randomly")
        parser.add_option("--idx_cnt", dest="index_count", type="int", default=0,
                          help="no of indexes to be created on datasets, default=0")
        parser.add_option("--syn_cnt", dest="synonym_count", type="int", default=0,
                          help="no of synonyms to be created, default=0")
        parser.add_option("--data_src", dest="data_source", default="gideon",
                          help="name of the data loader that was used to load data. Values - gideon, catapult")

        # Required if remote datasets need to be created or recreated
        parser.add_option("--rlink_cnt", dest="remote_link_count", type="int", default=0,
                          help="no of links to be created, default=0")
        parser.add_option("--remote_host", dest="remote_host", default="",
                          help="remote server ip with port <ip>:<port>")
        parser.add_option("--remote_usr", dest="remote_username", default="Administrator",
                          help="user name default=Administrator")
        parser.add_option("--remote_pwd", dest="remote_password", default="password",
                          help="password default=password")

        # Required if operation type is drop_cbas_infra
        parser.add_option("--drop_dataverse_percentage", dest="drop_dataverse_percentage", type="int", default=100,
                          help="Percentage of dataverses to be dropped")
        parser.add_option("--drop_dataset_percentage", dest="drop_dataset_percentage", type="int", default=100,
                          help="Percentage of datasets to be dropped")
        parser.add_option("--drop_link_percentage", dest="drop_link_percentage", type="int", default=100,
                          help="Percentage of links to be dropped")
        parser.add_option("--drop_index_percentage", dest="drop_index_percentage", type="int", default=100,
                          help="Percentage of indexes to be dropped")
        parser.add_option("--drop_synonym_percentage", dest="drop_synonym_percentage", type="int", default=100,
                          help="Percentage of synonyms to be dropped")

        # Required if operation type is recreate_cbas_infra
        parser.add_option("--recreate_dv", dest="recreate_dataverse_percentage", type="int", default=100,
                          help="Percentage of dataverses to be recreated")
        parser.add_option("--recreate_ds", dest="recreate_dataset_percentage", type="int", default=100,
                          help="Percentage of datasets to be recreated")
        parser.add_option("--recreate_lnk", dest="recreate_link_percentage", type="int", default=100,
                          help="Percentage of links to be recreated")
        parser.add_option("--recreate_idx", dest="recreate_index_percentage", type="int", default=100,
                          help="Percentage of indexes to be recreated")
        parser.add_option("--recreate_syn", dest="recreate_synonym_percentage", type="int", default=100,
                          help="Percentage of synonyms to be recreated")

        # Required if operation type is 'create_drop_dataverse_dataset_in_loop',
        # 'create_drop_dataverse_remote_dataset_in_loop'
        parser.add_option("--interval", dest="interval", type=int, default=60,
                          help="Interval between 2 create/drop dataverse/dataset statements when running in a loop")
        parser.add_option("-t", dest="timeout", type=int, default=0,
                          help="Timeout for create/drop dataverse/dataset loop. 0 (default) is infinite")

        parser.add_option("--api_timeout", dest="api_timeout", type=int, default=300,
                          help="No of threads to be executed in parallel")

        # Optionally required for operations - create_drop_dataverse_dataset_in_loop, create_cbas_infra,
        # recreate_cbas_infra. Not required for drop_cbas_infra.
        parser.add_option("-w", dest="wait_for_ingestion", choices=["true", "false"],
                          default="true", help="wait for data ingestion to complete in dataset, default=true")
        parser.add_option("--ingestion_timeout", dest="ingestion_timeout", type="int", default=3600,
                          help="time to wait for ingestion to finish for all datasets, default=3600")

        # Optionally required for operations - create_drop_dataverse_dataset_in_loop, create_cbas_infra,
        # recreate_cbas_infra. Not required for drop_cbas_infra.
        parser.add_option("--ds_without_where", dest="dataset_without_where_clause_percentage",
                          type="int", default=0, help="Percentage of datasets to be created without any where clause")

        self.options, args = parser.parse_args()

        if self.options.host is None or self.options.operations is None or self.options.buckets is None:
            print("Hostname, operations and buckets are mandatory")
            parser.print_help()
            exit(1)

        self.buckets = self.options.buckets.split(",")
        self.include_scopes = []
        self.exclude_scopes = []
        self.include_collections = []
        self.exclude_collections = []

        if self.options.include_scopes:
            self.include_scopes = self.options.include_scopes.split(",")
        if self.options.exclude_scopes:
            self.exclude_scopes = self.options.exclude_scopes.split(",")
        if self.options.include_collections:
            self.include_collections = self.options.include_collections.split(",")
        if self.options.exclude_collections:
            self.exclude_collections = self.options.exclude_collections.split(",")

        # If both include and exclude lists contains same entities, then assign empty list to exclude.
        if set(self.include_scopes) == set(self.exclude_scopes):
            self.exclude_scopes = []
        if set(self.include_collections) == set(self.exclude_collections):
            self.exclude_collections = []

        self.log = logging.getLogger("analyticsmanager")
        self.log.setLevel(logging.INFO)
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        ch.setFormatter(formatter)
        self.log.addHandler(ch)
        timestamp = str(datetime.now().strftime('%Y%m%dT_%H%M%S'))
        fh = logging.FileHandler("./analyticsmanager-{0}.log".format(timestamp))
        fh.setFormatter(formatter)
        self.log.addHandler(fh)

        if self.options.operations != "recreate_cbas_infra":
            self.set_max_counters()

        if self.options.operations == "create_drop_dataverse_dataset_in_loop":
            if self.options.remote_link_count > 0:
                self.create_drop_dataverse_dataset_in_loop(True, self.options.timeout, self.options.interval)
            else:
                self.create_drop_dataverse_dataset_in_loop(False, self.options.timeout, self.options.interval)
        elif self.options.operations == "create_cbas_infra":
            if self.options.remote_link_count > 0:
                self.create_cbas_infra(True)
                is_replica_set, content, response = self.set_replica()
                if is_replica_set and content['numReplicas'] == self.options.replica_count:
                if is_replica_set and content['numReplicas'] == self.options.replica_count:
                    self.log.info("Replica is set")
                else:
                    self.log.info("Replica is not set")
            else:
                self.create_cbas_infra(False)
                is_replica_set, content, response = self.set_replica()
                if is_replica_set and content['numReplicas'] == self.options.replica_count:
                    self.log.info("Replica is set")
                else:
                    self.log.info("Replica is not set")
        elif self.options.operations == "drop_cbas_infra":
            self.drop_cbas_infra()
        elif self.options.operations == "recreate_cbas_infra":
            self.recreate_cbas_infra()
            is_replica_set, content, response = self.set_replica()
            if is_replica_set and content['numReplicas'] == self.options.replica_count:
                self.log.info("Replica is set")
            else:
                self.log.info("Replica is not set")

    def set_max_counters(self):
        def inner_func(func_name):
            items = func_name()
            counters = [0]
            for item in items:
                if item == "Default":
                    continue
                counters.append(int(item.split("_")[-1]))
            return max(counters)
        global DATAVERSE_MAX_COUNTER, DATASET_MAX_COUNTER, INDEX_MAX_COUNTER, SYNONYM_MAX_COUNTER, LINK_MAX_COUNTER
        DATAVERSE_MAX_COUNTER = inner_func(self.get_all_dataverses)
        DATASET_MAX_COUNTER = inner_func(self.get_all_datasets)
        INDEX_MAX_COUNTER = inner_func(self.get_all_indexes)
        SYNONYM_MAX_COUNTER = inner_func(self.get_all_synonyms)
        LINK_MAX_COUNTER = inner_func(self.get_all_links)

    def get_all_collection_names(self, use_remote_host=False):
        collection_names = list()
        for bucket in self.buckets:
            self.log.info("Fetching collections in bucket {0}".format(bucket))
            bucket = bucket.strip("`")
            url = bucket + "/scopes"
            retry_attempt = 0
            while True:
                passed, content, response = self.api_call(
                    url, "GET", use_remote_host=use_remote_host)
                retry_attempt += 1
                if passed:
                    break
                elif retry_attempt > 5:
                    exit(1)
                time.sleep(10)
            scopes_dict = content["scopes"]
            for scope in scopes_dict:
                if self.include_scopes and scope["name"] not in \
                        self.include_scopes:
                    continue
                if self.exclude_scopes and scope["name"] in \
                        self.exclude_scopes:
                    continue
                for collection in scope["collections"]:
                    if self.include_collections and collection["name"] not \
                            in self.include_collections:
                        continue
                    if self.exclude_collections and collection["name"] in \
                            self.exclude_collections:
                        continue
                    name = ".".join([bucket, scope["name"], collection[
                        "name"]])
                    collection_names.append(self.format_name(name))
        self.log.info(str(collection_names))
        return collection_names

    def format_name(self, *args):
        """
        Enclose the name in `` if the name consist of - or starts with a number.
        """
        full_name = list()
        for name in args:
            if name:
                for _ in name.split("."):
                    _ = _.strip("`")
                    if _[0].isdigit() or ("-" in _):
                        full_name.append("`{0}`".format(_))
                    else:
                        full_name.append(_)
        return '.'.join(full_name)

    def set_replica(self):
        headers = {'Content-Type': 'application/x-www-form-urlencoded',
                   'Connection': 'close',
                   'Accept': '*/*'}
        url = "http://" + self.options.host + ":8091/settings/analytics"
        http = httplib2.Http(timeout=self.options.api_timeout)
        http.add_credentials(self.options.username, self.options.password)
        params = {"numReplicas":  self.options.replica_count}
        params = urllib.urlencode(params)
        try:
            response, content = http.request(uri=url, method="POST", headers=headers, body=params)
            if response['status'] in ['200', '201', '202']:
                return True, json.loads(content), response
            else:
                return False, content, response
        except Exception as err:
            self.log.error(str(err))
            time.sleep(10)
            return False, "", ""

    def create_dataverse(self, dataverse):
        self.log.info("Creating dataverse -- {0}".format(dataverse))
        cmd = "create dataverse {0};".format(dataverse)
        result, content, response = self.cbas_api_call(statement=cmd)
        if result:
            self.log.info("Created dataverse -- {0}".format(dataverse))
        else:
            self.log.error("Failed to Create dataverse -- {0}".format(dataverse))
            self.log.error(str(content))
            self.log.error(str(response))
        return result

    def drop_dataverse(self, dataverse):
        self.log.info("Dropping dataverse -- {0}".format(dataverse))
        cmd = "drop dataverse {0} if exists;".format(dataverse)
        result, content, response = self.cbas_api_call(statement=cmd)
        if result:
            self.log.info("Dropped dataverse -- {0}".format(dataverse))
        else:
            self.log.error("Failed to drop dataverse -- {0}".format(dataverse))
            self.log.error(str(content))
            self.log.error(str(response))
        return result

    def create_dataset(self, dataset, collection_name, compress_dataset=False, link=None, where_clause=True):
        self.log.info("Creating dataset {0} on {1}".format(dataset, collection_name))
        cmd = "create dataset {0}".format(dataset)
        if compress_dataset:
            cmd += " with {'storage-block-compression': {'scheme': 'snappy'}}"
        cmd += " on {0}".format(collection_name)
        if link:
            cmd += " at {0}".format(link)
        if where_clause:
            if self.options.data_source == "gideon":
                where = GIDEON_WHERE_CLAUSE_TEMPLATES
            else:
                where = CATAPULT_WHERE_CLAUSE_TEMPLATES
            cmd += " where {0}".format(random.choice(where))
        cmd += ";"
        self.log.info(cmd)
        result, content, response = self.cbas_api_call(statement=cmd)
        if result:
            self.log.info("Created dataset {0} on {1}".format(dataset,collection_name))
        else:
            self.log.error("Failed to Create dataset {0} on {1}".format(dataset,collection_name))
            self.log.error(str(content))
            self.log.error(str(response))
        return result

    def drop_dataset(self, dataset):
        self.log.info("Dropping dataset -- {0}".format(dataset))
        cmd = "drop dataset {0} if exists;".format(dataset)
        result, content, response = self.cbas_api_call(statement=cmd)
        if result:
            self.log.info("Dropped dataset -- {0}".format(dataset))
        else:
            self.log.error("Failed to drop dataset -- {0}".format(dataset))
            self.log.error(str(content))
            self.log.error(str(response))
        return result

    def create_index_on_dataset(self, dataset, index_name):
        if self.options.data_source == "gideon":
            index_templates = GIDEON_INDEX_TEMPLATES
        else:
            index_templates = CATAPULT_INDEX_TEMPLATES

        indexed_fields = index_templates[random.randrange(
            len(index_templates))]
        self.log.info(
            "Creating index {0} on {1} with indexed fields as {2};".format(
                index_name, dataset, indexed_fields))

        cmd = "create index {0} on {1}{2};".format(
            index_name, dataset, indexed_fields)
        result, content, response = self.cbas_api_call(statement=cmd)
        if result:
            self.log.info(
                "Created index {0} on {1} with indexed fields as {2};".format(
                    index_name, dataset, indexed_fields))
        else:
            self.log.error(
                "Failed to Create index {0} on {1} with indexed fields as {"
                "2};".format(index_name, dataset, indexed_fields))
            self.log.error(str(content))
            self.log.error(str(response))
        return result

    def drop_index(self, full_index_name):
        self.log.info("Dropping index -- {0}".format(full_index_name))
        cmd = "drop index {0} if exists;".format(full_index_name)
        result, content, response = self.cbas_api_call(statement=cmd)
        if result:
            self.log.info("Dropped index -- {0}".format(full_index_name))
        else:
            self.log.error("Failed to drop index -- {0}".format(full_index_name))
            self.log.error(str(content))
            self.log.error(str(response))
        return result

    def create_synonym(self, synonym_full_name, cbas_entity_full_name):
        self.log.info("Creating synonym {0} on {1}".format(
                synonym_full_name, cbas_entity_full_name))
        cmd = "create analytics synonym {0} If Not Exists for {1};".format(
            synonym_full_name, cbas_entity_full_name)
        result, content, response = self.cbas_api_call(statement=cmd)
        if result:
            self.log.info("Created synonym {0} on {1}".format(
                synonym_full_name, cbas_entity_full_name))
        else:
            self.log.error("Failed to Create synonym {0} on {1}".format(
                synonym_full_name, cbas_entity_full_name))
            self.log.error(str(content))
            self.log.error(str(response))
        return result

    def drop_synonym(self, synonym_full_name):
        self.log.info("Dropping Synonym -- {0}".format(synonym_full_name))
        cmd = "drop analytics synonym {0} If Exists;".format(synonym_full_name)
        result, content, response = self.cbas_api_call(statement=cmd)
        if result:
            self.log.info("Dropped Synonym -- {0}".format(synonym_full_name))
        else:
            self.log.error("Failed to drop Synonym -- {0}".format(
                synonym_full_name))
            self.log.error(str(content))
            self.log.error(str(response))
        return result

    def get_certs(self):
        pass

    def create_remote_link(self, link_name, dataverse, remote_host,
                           remote_username, remote_password,
                           encryption="none"):
        params = dict()
        params["name"] = link_name
        params["scope"] = dataverse
        params["type"] = "couchbase"
        params["hostname"] = remote_host
        params["username"] = remote_username
        params["password"] = remote_password
        params["encryption"] = encryption

        if encryption.lower() == "full":
            all_certs = random.choice([True,False])
            if all_certs:
                params["certificate"], params["clientCertificate"], params[
                    "clientKey"] = self.get_certs()
                del params["username"]
                del params["password"]
            else:
                params["certificate"] = self.get_certs()

        params = httplib2.urllib.urlencode(params)
        headers = {'content-type': 'application/x-www-form-urlencoded'}
        url = "http://" + self.options.host + ":8095/analytics/link"
        http = httplib2.Http(timeout=self.options.api_timeout)
        http.add_credentials(self.options.username, self.options.password)
        try:
            response, content = http.request(
                uri=url, method="POST", headers=headers, params=params)
            if response['status'] in ['200', '201', '202']:
                self.log.info("Created remote link {0}".format(link_name))
                return True
            else:
                self.log.error("Failed to Create remote link {0}".format(
                    link_name))
                self.log.error(str(content))
                self.log.error(str(response))
                return False
        except Exception as err:
            self.log.error(str(err))
            time.sleep(10)
            return False

    def drop_link(self, link):
        cmd = "drop link {0} if exists;".format(link)
        result, content, response = self.cbas_api_call(statement=cmd)
        if result:
            self.log.info("Dropped link -- {0}".format(link))
        else:
            self.log.error("Failed to drop link -- {0}".format(link))
            self.log.error(str(content))
            self.log.error(str(response))
        return result

    def get_pending_mutation_stats(self):
        self.log.info("Fetching pending mutations for all Analytics datasets")
        headers = {'content-type': 'application/x-www-form-urlencoded'}
        url = "http://" + self.options.host + \
              ":8095/analytics/node/agg/stats/remaining"
        http = httplib2.Http(timeout=self.options.api_timeout)
        http.add_credentials(self.options.username, self.options.password)
        while True:
            try:
                response, content = http.request(
                    uri=url, method="GET", headers=headers)
                if response['status'] in ['200', '201', '202']:
                    content = json.loads(content)
                    return True, content, response
                else:
                    self.error.log(
                        "Error while fetching pending mutations for all datasets")
                    self.log.error(str(content))
                    self.log.error(str(response))
                    return False, content, response
            except Exception as err:
                self.log.error(str(err))
                time.sleep(10)
                return False, "", ""

    def wait_for_ingestion_complete(self, datasets):
        datasets = datasets[:]
        ingestion_end_time = time.time() + self.options.ingestion_timeout
        while datasets and time.time() < ingestion_end_time:
            retry = 0
            while retry < 10:
                result, content, response = self.get_pending_mutation_stats()
                if result:
                    break
                time.sleep(60)
                retry += 1
            if result:
                for dataset in datasets:
                    self.log.info(
                        "Waiting for data ingestion to complete for dataset "
                        "{0}".format(dataset))
                    split_dataset_name = dataset.split(".")
                    dataverse_name = ".".join(split_dataset_name[:-1])
                    dataset_name = split_dataset_name[-1]
                    try:
                        if content[dataverse_name][dataset_name]["seqnoLag"] == 0:
                            self.log.info("Data ingestion completed for "
                                          "dataset {0}".format(dataset))
                            datasets.remove(dataset)
                    except KeyError:
                        pass
        if datasets:
            self.error.log("Error while fetching pending mutation for "
                           "dataset - {0}".format(datasets))

    def get_all_dataverses(self, display_form=True):
        if display_form:
            cmd = "select value regexp_replace(dv.DataverseName,\"/\"," \
                  "\".\") from Metadata.`Dataverse` as dv where " \
                  "dv.DataverseName != \"Metadata\";"
        else:
            cmd = "select value dv.DataverseName from Metadata.`Dataverse` " \
                  "as dv where dv.DataverseName != \"Metadata\";"
        status, content, _ = self.cbas_api_call(cmd)
        if status:
            return content["results"]

    def get_all_datasets(self, dataverses=[]):
        if not dataverses:
            dvs = self.get_all_dataverses(False)
        else:
            dvs = copy.deepcopy(dataverses)
            dvs = self.convert_name_to_non_display_form(dvs)
        dvs = json.dumps(dvs, encoding="utf-8").replace("\'", "\"")
        cmd = "select value regexp_replace(ds.DataverseName,\"/\",\".\") || " \
              "\".\" || ds.DatasetName from Metadata.`Dataset` as ds " \
              "where ds.DataverseName in {0};".format(dvs)
        status, content, _ = self.cbas_api_call(cmd)
        if status:
            return content["results"]
        else:
            return None

    def get_all_links(self, dataverses=[]):
        if not dataverses:
            dvs = self.get_all_dataverses(False)
        else:
            dvs = copy.deepcopy(dataverses)
            dvs = self.convert_name_to_non_display_form(dvs)
        dvs = json.dumps(dvs, encoding="utf-8").replace("\'", "\"")
        cmd = "select value regexp_replace(ln.DataverseName,\"/\",\".\") || " \
              "\".\" || ln.Name from Metadata.`Link` as ln where " \
              "ln.DataverseName in {0} and ln.Name != \"Local\";".format(dvs)
        status, content, _ = self.cbas_api_call(cmd)
        if status:
            return content["results"]
        else:
            return None

    def get_all_synonyms(self, dataverses=[]):
        if not dataverses:
            dvs = self.get_all_dataverses(False)
        else:
            dvs = copy.deepcopy(dataverses)
            dvs = self.convert_name_to_non_display_form(dvs)
        dvs = json.dumps(dvs, encoding="utf-8").replace("\'", "\"")
        cmd = "select value regexp_replace(syn.DataverseName,\"/\",\".\") " \
              "|| \".\" || syn.SynonymName from Metadata.`Synonym` as syn " \
              "where syn.DataverseName in {0};".format(dvs)
        status, content, _ = self.cbas_api_call(cmd)
        if status:
            return content["results"]
        else:
            return None

    def get_all_indexes(self):
        cmd = "select value regexp_replace(idx.DataverseName,\"/\",\".\") " \
              "|| \".\" || idx.DatasetName || \".\" || idx.IndexName " \
              "from Metadata.`Index` as idx where IsPrimary=False;"
        status, content, _ = self.cbas_api_call(cmd)
        if status:
            return content["results"]
        else:
            return None

    def create_drop_dataverse_dataset_in_loop(
            self, remote_datasets=False, timeout=3600, interval=60):
        end_time = 0
        if timeout > 0:
            end_time = time.time() + timeout

        dataverses = ["Default"]
        datasets = list()
        indexes = list()
        synonyms = list()
        remote_links = list()
        global DATAVERSE_MAX_COUNTER, DATASET_MAX_COUNTER, \
            INDEX_MAX_COUNTER, SYNONYM_MAX_COUNTER, LINK_MAX_COUNTER

        local_collection_names = self.get_all_collection_names()
        if remote_datasets:
            remote_collection_names = self.get_all_collection_names(
                use_remote_host=True)
        while True:
            if remote_datasets and not remote_links:
                dataverse_name = random.choice(dataverses)
                LINK_MAX_COUNTER += 1
                remote_links.append(".".join(
                    [dataverse_name, REMOTE_LINK_PREFIX.format(
                        LINK_MAX_COUNTER)]))
                if not self.create_remote_link(
                        REMOTE_LINK_PREFIX.format(LINK_MAX_COUNTER),
                        dataverse_name, self.options.remote_host,
                        self.options.remote_username,
                        self.options.remote_password,
                        random.choice(["none", "half"])):
                    remote_links.pop()
            elif not datasets:
                dataverse_name = random.choice(dataverses)
                DATASET_MAX_COUNTER += 1
                datasets.append(".".join(
                    [dataverse_name,
                     DATASET_PREFIX.format(DATASET_MAX_COUNTER)]))
                if not self.create_dataset(
                        datasets[-1], random.choice(local_collection_names),
                        random.choice([True, False, False, False]), None,
                        True):
                    datasets.pop()
                if self.options.wait_for_ingestion == "true":
                    self.wait_for_ingestion_complete(datasets)
            else:
                action = random.choice(["create", "create", "drop", "create"])
                if remote_datasets:
                    cbas_entity = random.choice(
                        ["dataverse", "dataset", "index", "dataset", "link",
                         "dataset", "index", "dataset", "synonym"])
                    create_remote_dataset = random.choice([True, False])
                else:
                    cbas_entity = random.choice(
                        ["dataverse", "dataset", "dataset", "dataset",
                         "index", "dataset", "synonym"])
                    create_remote_dataset = False

                if action == "create":
                    if cbas_entity == "dataverse":
                        DATAVERSE_MAX_COUNTER += 1
                        dataverses.append(random.choice(
                            [DATAVERSE_PREFIX_1,DATAVERSE_PREFIX_2]).format(
                            DATAVERSE_MAX_COUNTER))
                        if not self.create_dataverse(dataverses[-1]):
                            dataverses.pop()
                    elif cbas_entity == "dataset":
                        if create_remote_dataset:
                            collection_name = random.choice(
                                remote_collection_names)
                            link = random.choice(remote_links)
                        else:
                            collection_name = random.choice(
                                local_collection_names)
                            link = None
                        dataverse_name = random.choice(dataverses)
                        DATASET_MAX_COUNTER += 1
                        datasets.append(".".join(
                            [dataverse_name,
                             DATASET_PREFIX.format(DATASET_MAX_COUNTER)]))
                        if not self.create_dataset(
                                datasets[-1], collection_name,
                                random.choice([True, False, False, False]),
                                link, True):
                            datasets.pop()
                        if self.options.wait_for_ingestion == "true":
                            self.wait_for_ingestion_complete(datasets)
                    elif cbas_entity == "link":
                        dataverse_name = random.choice(dataverses)
                        LINK_MAX_COUNTER += 1
                        remote_links.append(".".join(
                            [dataverse_name,
                             REMOTE_LINK_PREFIX.format(LINK_MAX_COUNTER)]))
                        if not self.create_remote_link(
                                REMOTE_LINK_PREFIX.format(LINK_MAX_COUNTER),
                                dataverse_name, self.options.remote_host,
                                self.options.remote_username,
                                self.options.remote_password,
                                random.choice(["none", "half"])):
                            remote_links.pop()
                    elif cbas_entity == "index":
                        dataset_name = random.choice(datasets)
                        INDEX_MAX_COUNTER += 1
                        indexes.append(".".join(
                            [dataset_name, INDEX_PREFIX.format(
                                INDEX_MAX_COUNTER)]))
                        if not self.create_index_on_dataset(
                                dataset_name,
                                INDEX_PREFIX.format(INDEX_MAX_COUNTER)):
                            indexes.pop()
                    elif cbas_entity == "synonym":
                        dataverse_name = random.choice(dataverses)
                        dataset_name = random.choice(datasets+synonyms)
                        SYNONYM_MAX_COUNTER += 1
                        synonyms.append(".".join(
                            [dataverse_name, SYNONYM_PREFIX.format(
                                SYNONYM_MAX_COUNTER)]))
                        if not self.create_synonym(synonyms[-1], dataset_name):
                            synonyms.pop()
                else:
                    if cbas_entity == "dataverse":
                        dataverse_name = random.choice(dataverses)
                        for dataset in self.get_all_datasets([dataverse_name]):
                            # Only drop those datasets which were created by
                            # this method.
                            if dataset in datasets:
                                self.drop_dataset(dataset)
                                datasets.remove(dataset)
                        if dataverse_name != "Default":
                            self.drop_dataverse(dataverse_name)
                            dataverses.remove(dataverse_name)
                    elif cbas_entity == "dataset":
                        dataset = random.choice(datasets)
                        datasets.remove(dataset)
                        self.drop_dataset(dataset)
                    elif cbas_entity == "link" and remote_links:
                        link = random.choice(remote_links)
                        remote_links.remove(link)
                        self.drop_link(link)
                    elif cbas_entity == "index" and indexes:
                        index = random.choice(indexes)
                        indexes.remove(index)
                        self.drop_index(index)
                    elif cbas_entity == "synonym" and synonyms:
                        synonym = random.choice(synonyms)
                        synonyms.remove(synonym)
                        self.drop_synonym(synonym)

            # Exit if timed out
            if timeout > 0 and time.time() > end_time:
                break
            # Wait for the interval before doing the next CRUD operation
            time.sleep(interval)

    def create_cbas_infra(self, remote_datasets=False):
        dataverses = {"Default": 0}
        datasets = list()
        synonyms = list()
        remote_links = list()

        local_collection_names = self.get_all_collection_names()
        if remote_datasets:
            remote_collection_names = self.get_all_collection_names(
                use_remote_host=True)
        if self.options.dataverse_count > 1:
            for i in range(
                    DATAVERSE_MAX_COUNTER + 1,
                    DATAVERSE_MAX_COUNTER + self.options.dataverse_count + 1):
                name = random.choice([DATAVERSE_PREFIX_1,
                                      DATAVERSE_PREFIX_2]).format(i)
                dataverses[name] = 0
                if not self.create_dataverse(name):
                    self.log.error(
                        "FAILED : Creating Dataverse {0}".format(name))
                    del dataverses[name]

        for i in range(
                LINK_MAX_COUNTER + 1,
                LINK_MAX_COUNTER + self.options.remote_link_count + 1):
            dataverse_name = random.choice(dataverses.keys())
            remote_links.append(".".join(
                [dataverse_name, REMOTE_LINK_PREFIX.format(i)]))
            if not self.create_remote_link(
                    REMOTE_LINK_PREFIX.format(i), dataverse_name,
                    self.options.remote_host, self.options.remote_username,
                    self.options.remote_password,
                    random.choice(["none", "half"])):
                self.log.error(
                    "FAILED : Creating Remote Link {0}".format(
                        remote_links[-1]))
                remote_links.pop()

        ds_per_dv = 0
        if self.options.dataset_distribution == "uniform":
            ds_per_dv = -(
                    self.options.dataset_count // -self.options.dataverse_count)

        num_of_dataset_without_where_clause = (self.options.dataset_count *
                                               self.options.dataset_without_where_clause_percentage) / 100

        for i in range(
                DATASET_MAX_COUNTER + 1,
                DATASET_MAX_COUNTER + self.options.dataset_count + 1):
            if remote_datasets:
                create_remote_dataset = random.choice([True, False])
            else:
                create_remote_dataset = False
            if create_remote_dataset:
                collection_name = random.choice(remote_collection_names)
                link = random.choice(remote_links)
            else:
                collection_name = random.choice(local_collection_names)
                link = None

            dataverse_name = random.choice(dataverses.keys())
            if ds_per_dv:
                while True:
                    if dataverses[dataverse_name] < ds_per_dv:
                        dataverses[dataverse_name] += 1
                        break
                    dataverse_name = random.choice(dataverses.keys())

            datasets.append(".".join([dataverse_name, DATASET_PREFIX.format(i)]))

            if num_of_dataset_without_where_clause > 0:
                where = False
                num_of_dataset_without_where_clause -= 1
            else:
                where = True

            if not self.create_dataset(
                    datasets[-1], collection_name,
                    random.choice([True, False, False, False]), link, where):
                self.log.error("FAILED : Creating Dataset {0}".format(datasets[-1]))
                datasets.pop()
        if self.options.wait_for_ingestion == "true":
            self.wait_for_ingestion_complete(datasets)

        for i in range(
                INDEX_MAX_COUNTER + 1,
                INDEX_MAX_COUNTER + self.options.index_count + 1):
            dataset_name = random.choice(datasets)
            if not self.create_index_on_dataset(dataset_name,
                                                INDEX_PREFIX.format(i)):
                self.log.error(
                    "FAILED : Creating Index {0} on Dataset {1}".format(
                    INDEX_PREFIX.format(i), dataset_name))

        for i in range(
                SYNONYM_MAX_COUNTER + 1,
                SYNONYM_MAX_COUNTER + self.options.synonym_count + 1):
            dataverse_name = random.choice(dataverses.keys())
            dataset_name = random.choice(datasets + synonyms)
            synonyms.append(".".join([dataverse_name, SYNONYM_PREFIX.format(i)]))
            if not self.create_synonym(synonyms[-1], dataset_name):
                self.log.error(
                    "FAILED : Creating Synonym {0}".format(synonyms[-1]))
                synonyms.pop()

    def drop_cbas_infra(self):

        def dataverses_to_be_deleted():
            if self.options.drop_dataverse_percentage == 100:
                max_counter = 0
            else:
                max_counter = DATAVERSE_MAX_COUNTER
            dataverses = self.get_all_dataverses()
            no_of_items_to_be_dropped = (self.options.drop_dataverse_percentage * len(dataverses)) / 100

            if "Default" in dataverses:
                dataverses.remove("Default")
                no_of_items_to_be_dropped -= 1

            dataverse_to_be_deleted = list()
            while no_of_items_to_be_dropped > 0:
                item = random.choice(dataverses)
                if (max_counter == int(item.split("_")[-1])) or item == "Default":
                    continue
                else:
                    dataverse_to_be_deleted.append(item)
                    dataverses.remove(item)
                    no_of_items_to_be_dropped -= 1
            return dataverse_to_be_deleted

        def inner_func(get_func, drop_percentage, drop_func, max_counter,
                       dataverses=[]):

            if drop_percentage == 100:
                max_counter = 0
            total_items = get_func()
            no_of_items_to_be_dropped = (drop_percentage * len(total_items)) / 100

            items_in_dataverses_to_be_deleted = None
            if dataverses:
                items_in_dataverses_to_be_deleted = get_func(dataverses)

            if items_in_dataverses_to_be_deleted:
                if len(items_in_dataverses_to_be_deleted) > no_of_items_to_be_dropped:
                    no_of_items_to_be_dropped = len(items_in_dataverses_to_be_deleted)

            while no_of_items_to_be_dropped > 0:
                if items_in_dataverses_to_be_deleted:
                    item = random.choice(items_in_dataverses_to_be_deleted)
                    if max_counter == int(item.split("_")[-1]):
                        max_counter -= 1
                    items_in_dataverses_to_be_deleted.remove(item)
                else:
                    item = random.choice(total_items)
                if max_counter == int(item.split("_")[-1]):
                    continue
                else:
                    if drop_func(item):
                        total_items.remove(item)
                        no_of_items_to_be_dropped -= 1
                    else:
                        self.log.error("FAILED to Drop {0}".format(item))
                        if dataverses:
                            items_in_dataverses_to_be_deleted.append(item)

        # get list of dataverses to be deleted, so that datasets, synonyms and links from that dataverse
        # are deleted first
        dataverses = dataverses_to_be_deleted()

        if self.options.drop_index_percentage > 0:
            inner_func(
                self.get_all_indexes, self.options.drop_index_percentage,
                self.drop_index, INDEX_MAX_COUNTER)

        if self.options.drop_synonym_percentage > 0:
            inner_func(
                self.get_all_synonyms, self.options.drop_synonym_percentage,
                self.drop_synonym, SYNONYM_MAX_COUNTER, dataverses)
        if self.options.drop_dataset_percentage > 0:
            inner_func(
                self.get_all_datasets, self.options.drop_dataset_percentage,
                self.drop_dataset, DATASET_MAX_COUNTER, dataverses)
        if self.options.drop_link_percentage > 0:
            inner_func(
                self.get_all_links, self.options.drop_link_percentage,
                self.drop_link, LINK_MAX_COUNTER, dataverses)

        while dataverses:
            dataverse = dataverses.pop()
            if not self.drop_dataverse(dataverse):
                dataverses.append(dataverse)

    def recreate_cbas_infra(self):

        def get_dropped_items(list_of_items):
            if "Default" in list_of_items:
                low = 1
                list_of_items.remove("Default")
            else:
                low = 0
            if len(list_of_items) == low:
                # If no items are present then create 10 items of that type
                return [x for x in range(1, 11)]
            else:
                items_present = list()
                for item in list_of_items:
                    items_present.append(int(item.split("_")[-1]))
                return set(
                    [x for x in range(1, max(items_present))]) - set(items_present)

        dataverses = self.get_all_dataverses()
        if self.options.recreate_dataverse_percentage > 0:
            dropped_items = get_dropped_items(dataverses)
            counter = (self.options.recreate_dataverse_percentage * len(dropped_items)) / 100
            while dropped_items:
                if counter == 0:
                    break
                item = dropped_items.pop()
                dataverses.append(
                    random.choice([DATAVERSE_PREFIX_1,
                                   DATAVERSE_PREFIX_2]).format(item))
                if not self.create_dataverse(dataverses[-1]):
                    self.log.error(
                        "FAILED : Creating Dataverse {0}".format(
                            dataverses[-1]))
                    dataverses.pop()
                    dropped_items.append(item)
                else:
                    counter -= 1

        links = self.get_all_links()
        if self.options.recreate_link_percentage > 0 and self.options.remote_host:
            dropped_items = get_dropped_items(links)
            counter = (self.options.recreate_link_percentage * len(dropped_items)) / 100
            while dropped_items:
                if counter == 0:
                    break
                item = dropped_items.pop()
                dataverse_name = random.choice(dataverses)
                links.append(".".join(
                    [dataverse_name, REMOTE_LINK_PREFIX.format(item)]))
                if not self.create_remote_link(
                        REMOTE_LINK_PREFIX.format(item), dataverse_name,
                        self.options.remote_host, self.options.remote_username,
                        self.options.remote_password, random.choice(["none", "half"])):
                    self.log.error("FAILED : Creating Link {0}".format(links[-1]))
                    links.pop()
                    dropped_items.append(item)
                else:
                    counter -= 1

        datasets = self.get_all_datasets()
        if self.options.recreate_dataset_percentage > 0:
            dropped_items = get_dropped_items(datasets)
            counter = (self.options.recreate_dataset_percentage * len(dropped_items)) / 100

            local_collection_names = self.get_all_collection_names()
            if links:
                remote_collection_names = self.get_all_collection_names(use_remote_host=True)
            while dropped_items:
                if counter == 0:
                    break
                item = dropped_items.pop()
                if links:
                    create_remote_dataset = random.choice([True, False])
                else:
                    create_remote_dataset = False
                if create_remote_dataset:
                    collection_name = random.choice(remote_collection_names)
                    link = random.choice(links)
                else:
                    collection_name = random.choice(local_collection_names)
                    link = None

                dataverse_name = random.choice(dataverses)

                datasets.append(".".join([dataverse_name, DATASET_PREFIX.format(item)]))

                if not self.create_dataset(
                        datasets[-1], collection_name,
                        random.choice([True, False, False, False]), link, True):
                    self.log.error("FAILED : Creating Link {0}".format(datasets[-1]))
                    datasets.pop()
                    dropped_items.append(item)
                else:
                    counter -= 1
            if self.options.wait_for_ingestion == "true":
                self.wait_for_ingestion_complete(datasets)

        if self.options.recreate_index_percentage > 0:
            dropped_items = get_dropped_items(self.get_all_indexes())
            counter = (self.options.recreate_index_percentage * len(dropped_items)) / 100
            while dropped_items:
                if counter == 0:
                    break
                item = dropped_items.pop()
                dataset_name = random.choice(datasets)
                if not self.create_index_on_dataset(dataset_name, INDEX_PREFIX.format(item)):
                    dropped_items.append(item)
                else:
                    counter -= 1

        synonyms = self.get_all_synonyms()
        if self.options.recreate_synonym_percentage > 0:
            dropped_items = get_dropped_items(synonyms)
            counter = (self.options.recreate_synonym_percentage * len(dropped_items)) / 100
            while dropped_items:
                if counter == 0:
                    break
                item = dropped_items.pop()
                dataverse_name = random.choice(dataverses)
                dataset_name = random.choice(datasets + synonyms)
                synonyms.append(".".join([dataverse_name, SYNONYM_PREFIX.format(item)]))
                if not self.create_synonym(synonyms[-1], dataset_name):
                    synonyms.pop()
                    dropped_items.append(item)
                else:
                    counter -= 1

    def cbas_api_call(self, statement=None):
        headers = {'Content-Type': 'application/json',
                   'Connection': 'close',
                   'Accept': '*/*'}
        url = "http://" + self.options.host + ":8095/analytics/service"
        http = httplib2.Http(timeout=self.options.api_timeout)
        http.add_credentials(self.options.username, self.options.password)
        params = {'statement': statement, 'pretty': "true",
                  'client_context_id': None, 'timeout': "{0}s".format(self.options.api_timeout)}
        params = json.dumps(params)
        try:
            response, content = http.request(uri=url, method="POST", headers=headers, body=params)
            if response['status'] in ['200', '201', '202']:
                return True, json.loads(content, encoding="UTF-8"), response
            else:
                return False, content, response
        except Exception as err:
            self.log.error(str(err))
            time.sleep(10)
            return False, "", ""

    def api_call(self, url, method="GET", body=None, use_remote_host=False):

        headers = {'content-type': 'application/x-www-form-urlencoded'}
        http = httplib2.Http(timeout=self.options.api_timeout)

        if use_remote_host:
            url = "http://" + self.options.remote_host + ":8091/pools/default/buckets/" + url
            http.add_credentials(self.options.remote_username, self.options.remote_password)
        else:
            url = "http://" + self.options.host + ":8091/pools/default/buckets/" + url
            http.add_credentials(self.options.username, self.options.password)
        try:
            response, content = http.request(uri=url, method=method, headers=headers, body=body)
            if response['status'] in ['200', '201', '202']:
                return True, json.loads(content), response
            else:
                return False, content, response
        except Exception as err:
            self.log.error(str(err))
            time.sleep(10)
            return False, "", ""

    def convert_name_to_non_display_form(self, name):

        def inner_func(inner_name):
            inner_name = inner_name.split(".")
            inner_name = "/".join(inner_name)
            return inner_name

        if isinstance(name, str):
            return inner_func(name)

        elif isinstance(name, list):
            for i in range(0,len(name)):
                name[i] = inner_func(name[i])
            return name

if __name__ == "__main__":
    AnalyticsOperations().run()

import requests
import dns.resolver

import argparse
import subprocess
import logging
import time
import random
from string import ascii_letters, digits

class MagmaLoader:
    def __init__(self):
        self.host = None
        self.username = None
        self.password = None
        self.host = None
        self.srv = None
        self.count = 1
        self.bucket_name = None
        self.scope = None
        self.collection = None
        self.start = 0
        self.end = None
        self.percent_create = 100
        self.percent_update = 0
        self.percent_delete = 0
        self.key_prefix = "doc"
        self.ops_rate = None
        self.mutations_timeout = None
        self.value_type = "Hotel"
        self.model = None
        self.base64 = False
        self.workers = 1
        self.doc_size = 1024
        self.all_coll = False
        self.pd = 0
        self.pu = 0
        self.pc = 100
        self.tls = False
        self.port = 8091
        self.indexer_port = 9102
        self.protocol = "http"
        self.skip_default = False
        self.doc_template = "Hotel"
        self.mutations_mode = False
        self.sift_path = None
        self.log = logging.getLogger("magmaloader")
        self.log.setLevel(logging.INFO)

    def run(self):
        usage = '''%prog -n hostname(connection string) -u username -p password -b bucket -s scope_name -c collection_name
                    -pc percentage_create -pc percentage_delete -pu percentage_update -pd percentage_delete -kp key_prefix
                    --start start_num --end end_num --srv True/False --ops_rate ops_rate --all_coll True/False
                '''
        parser = argparse.ArgumentParser()
        parser.add_argument("--host", dest="host", help="connection string/server IP")
        parser.add_argument("--user", dest="username", default="Administrator", help="user name default=Administrator")
        parser.add_argument("--password", dest="password", default="password", help="password default=password")
        parser.add_argument("--bucket", dest="bucket", default="default", help="bucket, default=default")
        parser.add_argument("--scope", dest="scope", help="scope name")
        parser.add_argument("--collection", dest="collection", help="collection name")
        parser.add_argument("--start", dest="start", help="start sequence number")
        parser.add_argument("--end", dest="end", help="end sequence number")
        parser.add_argument("--pc", dest="percentage_create", help="Percentage of create mutations")
        parser.add_argument("--pu", dest="percentage_update", help="Percentage of update mutations")
        parser.add_argument("--pd", dest="percentage_delete", help="Percentage of update mutations")
        parser.add_argument("--ops_rate", dest="ops_rate", help="Rate of mutations")
        parser.add_argument("--model", dest="model", default= "sentence-transformers/all-MiniLM-L6-v2",
                            help="Vector embedding generation model")
        parser.add_argument("--base64", dest="base64", default="false",
                            help="Used Base64 encodings for Vector embeddings")
        parser.add_argument("--all_coll", dest="all_coll", help="True if data to be loaded on all collections", default="false")
        parser.add_argument("--srv", dest="srv", help="Set to true if host is SRV", default="false")
        parser.add_argument("--tls", dest="tls", help="Set to true if host is SRV", default="false")
        parser.add_argument("--skip_default", dest="skip_default", help="True if dataload needs to be skipped on default collection",
                            default="false")
        parser.add_argument("--sift_path", dest="sift_path", help="dataset path", default=None)
        parser.add_argument("--rr", dest="rr", help='Incremental data loading until indexer hits a specific resident ratio')
        parser.add_argument("--bucket_list", dest="bucket_list", help='A list of buckets passed in a comma seperated manner for data loading till a rr')
        parser.add_argument("--doc_template", dest="doc_template", help="doc template to be used for loader", default="Hotel")
        parser.add_argument("--mutations_mode", dest="mutations_mode", help="running magmaloader with max memory",
                            default="false")
        parser.add_argument("--mutations_timeout", dest="mutations_timeout", help="mutations timeout period in seconds",
                            default=3600)
        parser.add_argument("--num_workers", dest="num_workers", help="True if dataload needs to be skipped on default collection", default=10)
        args = parser.parse_args()
        self.host = args.host
        self.username = args.username
        self.password = args.password
        # self.list=options.list.split(",")
        self.tls = True if args.tls.lower() == 'true' else False
        self.ops_rate = args.ops_rate
        self.srv = True if args.srv.lower() == 'true' else False
        self.base64 = True if args.base64.lower() == 'true' else False
        self.pd = args.percentage_delete
        self.pu = args.percentage_update
        self.pc = args.percentage_create
        self.start = args.start
        self.end = args.end
        self.scope = args.scope
        self.collection = args.collection
        self.bucket_name = args.bucket
        self.model = args.model
        self.mutations_mode = args.mutations_mode.lower() == 'true'
        self.mutations_timeout = int(args.mutations_timeout)
        self.sift_path = args.sift_path
        if args.rr is None:
            self.rr = None
        else:
            self.rr = int(args.rr)
            self.bucket_list = args.bucket_list.split(",")
        self.doc_template = args.doc_template
        self.workers = int(args.num_workers)
        self.all_coll = True if args.all_coll.lower() == 'true' else False
        self.skip_default = True if args.skip_default.lower() == 'true' else False
        self.ops_rate = 40000 if not args.ops_rate else int(args.ops_rate)
        if self.tls:
            self.port = 18091
            self.protocol = "https"
        if self.host is None:
            self.log.info("Hostname is mandatory")
            parser.print_help()
            exit(1)
        if self.rr is None:
            if self.sift_path:
                self.load_sift_data(bucket_name=self.bucket_name)
            else:
                self.load_data(bucket_name=self.bucket_name)
        else:
            self.load_data_till_rr()

    def get_all_collections(self, bucket_name):
        if self.srv:
            host = self.fetch_rest_url(self.host)
        else:
            host = self.host
        url = f"{self.protocol}://{host}:{self.port}/pools/default/buckets/{bucket_name}/scopes"
        print(f"Url is {url}")
        response = requests.get(url, verify=False, auth=(self.username, self.password))
        resp_json = response.json()
        scope_coll_map = {}
        for item in resp_json['scopes']:
            if item['name'] not in ['_system']:
                scope = item['name']
                coll_list = [item2['name'] for item2 in item['collections']]
                scope_coll_map[scope] = coll_list
        return scope_coll_map

    def get_indexer_stats(self,node):
        url = f"{self.protocol}://{node}:{self.indexer_port}/stats"
        response = requests.get(url, verify=False, auth=(self.username, self.password))
        json_parsed = response.json()
        index_map = {}
        for key in list(json_parsed.keys()):
            tokens = key.split(":")
            val = json_parsed[key]
            if len(tokens) == 1:
                field = tokens[0]
                index_map[field] = val
            if len(tokens) == 3:
                if tokens[0] not in index_map:
                    index_map[tokens[0]] = dict()
                if tokens[1] not in index_map[tokens[0]]:
                    index_map[tokens[0]][tokens[1]] = dict()
                index_map[tokens[0]][tokens[1]][tokens[2]] = val
        return index_map

    def fetch_rest_url(self, url):
        """
        returns the hostname for the srv domain
        """
        srv_info = {}
        srv_records = dns.resolver.resolve('_couchbases._tcp.' + url, 'SRV')
        for srv in srv_records:
            srv_info['host'] = str(srv.target).rstrip('.')
            srv_info['port'] = srv.port
        return srv_info['host']

    def rr_reached(self):
        index_nodes = self.get_nodes_from_service_map()
        index_rr = []
        for node in index_nodes:
            index_rr.append(int(self.get_indexer_stats(node)['avg_resident_percent']))
        self.log.info(f"Current Resident Ratios of Index nodes - {index_rr}")
        value = any(self.rr >= x for x in index_rr)
        return value

    def load_data_till_rr(self):
        while not self.rr_reached():
            for bucket in self.bucket_list:
                self.load_data(random_key_prefix=True,bucket_name=bucket)
            time.sleep(60)
            self.log.info("Giving some time to Resident Ratio to settle down")


    def get_nodes_from_service_map(self, service='index', all_nodes=True):
        service_nodes = []
        url = f"{self.protocol}://{self.host}:{self.port}/pools/default"
        self.log.info(f"url is {url}")
        response = requests.get(url, verify=False, auth=(self.username, self.password))
        resp_json = response.json()
        for node in resp_json['nodes']:
            if service in node["services"]:
                service_nodes.append(node["otpNode"].split('@')[1])
        try:
            if not all_nodes:
                return service_nodes[0]
            else:
                return service_nodes
        except:
            raise Exception("service node list is empty")

    def load_data(self, random_key_prefix=False, bucket_name="default"):
        self.bucket_name = bucket_name
        if random_key_prefix:
            self.key_prefix = ''.join(random.choices(ascii_letters + digits, k=10))
        if self.all_coll:
            scope_coll_map = self.get_all_collections(self.bucket_name)
        else:
            scope_coll_map = {self.scope: [self.collection]}
        for scope in scope_coll_map:
            if scope == '_system':
                continue
            coll_list = scope_coll_map[scope]
            for coll in coll_list:
                if coll == '_default' and self.skip_default:
                    continue
                if not self.mutations_mode:
                    command = f"java -jar magmadocloader.jar -n {self.host} " \
                              f"-user '{self.username}' -pwd '{self.password}' -b {self.bucket_name} " \
                              f"-p 11207 -create_s {self.start} -create_e {self.end} " \
                              f"-cr {self.percent_create} -up {self.percent_update} -rd {self.percent_delete}" \
                              f" -docSize {self.doc_size} -keyPrefix {self.key_prefix} " \
                              f"-scope {scope} -collection {coll} " \
                              f"-workers {self.workers} -maxTTL 1800 -ops {self.ops_rate} -valueType {self.doc_template} "\
                              f"-model {self.model} -base64 {self.base64}"
                else:
                    command = f"java -Xmx512m -jar magmadocloader.jar -n {self.host} " \
                              f"-user '{self.username}' -pwd '{self.password}' -b {self.bucket_name} " \
                              f"-p 11207 -update_s {self.start} -update_e {self.end} " \
                              f"-cr 0 -up 100 -rd {self.percent_delete}" \
                              f" -docSize {self.doc_size} -keyPrefix {self.key_prefix} " \
                              f"-scope {scope} -collection {coll} " \
                              f"-workers {self.workers} -maxTTL 1800 -ops {self.ops_rate} -valueType {self.doc_template} " \
                              f"-model {self.model} -base64 {self.base64} -mutate 1  -mutation_timeout {self.mutations_timeout}"
                self.log.info("Will run this {}".format(command))
                proc = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
                out = proc.communicate()
                if proc.returncode != 0:
                    raise Exception("Exception in magma loader to {}".format(out))

    def load_sift_data(self, random_key_prefix=False, bucket_name="default"):
        self.bucket_name = bucket_name
        if random_key_prefix:
            self.key_prefix = ''.join(random.choices(ascii_letters + digits, k=10))
        if self.all_coll:
            scope_coll_map = self.get_all_collections(self.bucket_name)
        else:
            scope_coll_map = {self.scope: [self.collection]}
        for scope in scope_coll_map:
            if scope == '_system':
                continue
            coll_list = scope_coll_map[scope]
            for coll in coll_list:
                if coll == '_default' and self.skip_default:
                    continue
                command = f"java -cp magmadocloader.jar couchbase.test.sdk.SIFTLoader -n {self.host} " \
                          f"-user '{self.username}' -pwd '{self.password}' -b {self.bucket_name} " \
                          f"-create_s {self.start} -create_e {self.end} -cr {self.percent_create} " \
                          f"-scope {scope} -collection {coll} -p 11207 " \
                          f"-workers {self.workers} -ops {self.ops_rate} -valueType siftBigANN "\
                          f"-siftURL ftp://ftp.irisa.fr/local/texmex/corpus/bigann_base.bvecs.gz " \
                          f"-baseVectorsFilePath {self.sift_path}"
                # working siftloader
                # java -cp magmadocloader.jar couchbase.test.sdk.SIFTLoader -n  172.23.96.198 -user Administrator
                # -pwd 'password' -b bucket4 -p 11207 -create_s 0 -create_e 100 -cr 100 -docSize 1024
                # -keyPrefix doc1 -scope _default -collection _default -valueType siftBigANN
                # -siftURL ftp://ftp.irisa.fr/local/texmex/corpus/bigann_base.bvecs.gz -baseVectorsFilePath /data/bigann
                print("Will run this {}".format(command))
                proc = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
                out = proc.communicate()
                if proc.returncode != 0:
                    raise Exception("Exception in magma loader to {}".format(out))

if __name__ == '__main__':
    docloader = MagmaLoader()
    docloader.run()

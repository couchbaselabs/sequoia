import requests
import dns.resolver

import argparse
import subprocess
import logging

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
        self.workers = 1
        self.doc_size = 1024
        self.all_coll = False
        self.pd = 0
        self.pu = 0
        self.pc = 100
        self.tls = False
        self.port = 8091
        self.protocol = "http"
        self.skip_default = False
        self.log = logging.getLogger("indexmanager")
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
        parser.add_argument("--all_coll", dest="all_coll", help="True if data to be loaded on all collections", default="false")
        parser.add_argument("--srv", dest="srv", help="Set to true if host is SRV", default="false")
        parser.add_argument("--tls", dest="tls", help="Set to true if host is SRV", default="false")
        parser.add_argument("--skip_default", dest="skip_default", help="True if dataload needs to be skipped on default collection",
                            default="false")
        args = parser.parse_args()
        self.host = args.host
        self.username = args.username
        self.password = args.password
        # self.list=options.list.split(",")
        self.tls = True if args.tls.lower() == 'true' else False
        self.ops_rate = args.ops_rate
        self.srv = True if args.srv.lower() == 'true' else False
        self.pd = args.percentage_delete
        self.pu = args.percentage_update
        self.pc = args.percentage_create
        self.start = args.start
        self.end = args.end
        self.scope = args.scope
        self.collection = args.collection
        self.bucket_name = args.bucket
        self.all_coll = True if args.all_coll.lower() == 'true' else False
        self.skip_default = True if args.skip_default.lower() == 'true' else False
        self.ops_rate = 10000 if not args.ops_rate else int(args.ops_rate)
        if self.tls:
            self.port = 18091
            self.protocol = "https"
        if self.host is None :
            self.log.info("Hostname is mandatory")
            parser.print_help()
            exit(1)
        self.load_data()

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
            scope = item['name']
            coll_list = [item2['name'] for item2 in item['collections']]
            scope_coll_map[scope] = coll_list
        return scope_coll_map

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

    def load_data(self):
        if self.all_coll:
            scope_coll_map = self.get_all_collections(self.bucket_name)
        else:
            scope_coll_map = {self.scope: [self.collection]}
        for scope in scope_coll_map:
            coll_list = scope_coll_map[scope]
            for coll in coll_list:
                if coll == '_default' and self.skip_default:
                    continue
                command = f"java -jar magmadocloader.jar -n {self.host} " \
                          f"-user '{self.username}' -pwd '{self.password}' -b {self.bucket_name} " \
                          f"-p 11207 -create_s {self.start} -create_e {self.end} " \
                          f"-cr {self.percent_create} -up {self.percent_update} -rd {self.percent_delete}" \
                          f" -docSize {self.doc_size} -keyPrefix {self.key_prefix} " \
                          f"-scope {scope} -collection {coll} " \
                          f"-workers {self.workers} -maxTTL 1800 -ops {self.ops_rate} -valueType Hotel"
                self.log.info("Will run this {}".format(command))
                proc = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
                out = proc.communicate()
                if proc.returncode != 0:
                    raise Exception("Exception in magma loader to {}".format(out))

if __name__ == '__main__':
    docloader = MagmaLoader()
    docloader.run()

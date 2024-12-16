import argparse
import logging
import requests
import subprocess
from requests.auth import HTTPBasicAuth
import paramiko
import re


import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from couchbase.cluster import Cluster
from couchbase.options import ClusterOptions
from couchbase.auth import PasswordAuthenticator
from requests.exceptions import RequestException


class UpgradeWorkload:

    def __init__(self, cluster_ip, result_cluster_ip, bucket, scope, collection, select_queries, update_start, update_end, s3_bucket, doc_prefix='doc_', doc_size=500, workers=1, ops_rate=5000, doc_template='Hotel', diff_percent=20, mutation_timeout=10, username='Administrator', password='password', target_version='7.6.4', result_bucket='gsi_upgrade_test_bucket', r_username='Administrator', r_password='Password@123'):
        self.log = logging.getLogger('upgrade_workload')
        self.log.setLevel(logging.INFO)
        # Set up formatter
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self.log.addHandler(console_handler)

        # Disable propagation to avoid duplicate logs if using root-level configuration
        self.log.propagate = False

        # Test the logger
        self.log.info(f"Logging initialized.")

        self.cluster_ip = cluster_ip
        auth = PasswordAuthenticator(r_username, r_password)
        options = ClusterOptions(auth)
        options.apply_profile("wan_development")
        self.result_cluster = Cluster(f"couchbases://{result_cluster_ip}", options)
        self.bucket = bucket
        self.scope = scope
        self.collection = collection
        self.select_queries = select_queries
        self.update_start = update_start
        self.update_end = update_end
        self.mutation_timeout = mutation_timeout
        self.username = username
        self.password = password
        self.result_bucket = result_bucket
        self.doc_prefix = doc_prefix
        self.workers = workers
        self.doc_size = doc_size
        self.ops_rate = ops_rate
        self.doc_template = doc_template
        self.diff_percent = diff_percent
        self.target_version = target_version
        self.s3_bucket = s3_bucket


    def get_nodes_from_service_map(self, service='index', all_nodes=True):
        service_nodes = []
        url = f"http://{self.cluster_ip}:8091/pools/default"
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

    def query_runner(self, query, query_node):

        auth = (self.username, self.password)
        payload = {"statement": query}
        api = f"http://" + query_node + ':8093/query/service'
        try:
            response = requests.post(url=api, auth=auth, timeout=20, verify=False,
                                     headers={'Content-Type': 'application/json'}, json=payload)
            if response.status_code == 200:

                return True
        except:
            pass

    def get_indexer_stats(self, node):
        url = f"http://{node}:9102/stats"
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

    def run_scans(self, queries):
        query_node = self.get_nodes_from_service_map(service="n1ql", all_nodes=False)
        self.log.info(f"running query via rest")
        counter = 0
        while counter < self.mutation_timeout:
            with ThreadPoolExecutor() as executor_main:
                for query in queries:
                    query_task = executor_main.submit(self.query_runner, query, query_node)
                time.sleep(1)
                counter += 1

    def run_mutations(self):

        command = f"java -Xmx512m -jar magmadocloader.jar -n {self.cluster_ip} " \
                  f"-user '{self.username}' -pwd '{self.password}' -b {self.bucket} " \
                  f"-p 11207 -update_s {self.update_start} -update_e {self.update_end} " \
                  f"-cr 0 -up 100 " \
                  f" -docSize {self.doc_size} -keyPrefix {self.doc_prefix} " \
                  f"-scope {self.scope} -collection {self.collection} " \
                  f"-workers {self.workers} -maxTTL 1800 -ops {self.ops_rate} -valueType {self.doc_template} " \
                  f"-mutate 1  -mutation_timeout {self.mutation_timeout}"

        self.log.info("Will run this {}".format(command))
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
        out = proc.communicate()
        if proc.returncode != 0:
            raise Exception("Exception in magma loader to {}".format(out))

    def run_workload(self):
        with ThreadPoolExecutor() as executor_main:
            query_task = executor_main.submit(self.run_scans, self.select_queries)
            mutation_task = executor_main.submit(self.run_mutations)
            mutation_task.result()
        self.log.info("Workload finished sucessfully")

    def per_indexer_node_stats(self):
        stats_map = {}
        index_nodes = self.get_nodes_from_service_map(service="index", all_nodes=True)
        for node in index_nodes:
            key = f"{node}"
            index_stats = self.get_indexer_stats(node=node)
            stats_map[key] = index_stats

        return stats_map

    def compare_indexer_stats(self, stats_map_before, stats_map_after, stats_comparison_list=['memory_used', 'cpu_utilization']):
        diff_list = []
        for node_before, node_after in zip(stats_map_before, stats_map_after):
            for stats_before, stats_after in zip(stats_map_before[node_before], stats_map_after[node_after]):
                if stats_before in stats_comparison_list:
                    value_before = stats_map_before[node_before][stats_before]
                    value_after = stats_map_after[node_after][stats_after]
                    diff = value_after - value_before
                    threshold = (self.diff_percent/100) * value_before
                    if diff > threshold:
                        diff_list.append(f'for the stat {stats_before} value on node {node_before} before upgrade was {value_before} and value after upgrade on node {node_after} is {value_after}.')

        return diff_list

    def get_cluster_nodes(self):
        try:
            # Query the /pools/default endpoint to get cluster node information
            url = f'http://{self.cluster_ip}:8091/pools/default'
            response = requests.get(url=url, auth=(self.username, self.password), timeout=10)
            response.raise_for_status()

            # Extract node information
            data = response.json()
            nodes = data.get('nodes', [])
            return nodes
        except RequestException as e:
            self.log.info(f"Error while querying the Couchbase API: {e}")
            return None

    # Function to check the version of a given node
    def get_node_version(self, node):
        try:
            # Each node has a URI in the form of 'http://<hostname>:<port>'
            node_url = f"http://{node['hostname']}"
            self.log.info(f"url to check node version is {node_url}")

            # Query the node to get the version info
            response = requests.get(f'{node_url}/pools/default', auth=(self.username, self.password), timeout=10)
            response.raise_for_status()

            # Extract the version of the node
            data = response.json()
            node_version = data.get('nodes', [{}])[0].get('version', '').split('-')[0]
            return node_version
        except RequestException as e:
            # If the node is unreachable (e.g., due to an upgrade), log and skip the node
            self.log.info(f"Node {node['hostname']} is not reachable (likely being upgraded). Skipping... {e}")
            return None

    def check_all_nodes_upgraded(self, timeout=3600):
        start_time = time.time()

        while time.time() - start_time < timeout:
            self.log.info(f"Checking if all nodes are upgraded to version {self.target_version}...")

            # Get the list of nodes in the cluster
            nodes = self.get_cluster_nodes()
            if nodes is None:
                self.log.info("Error fetching node list. Retrying...")
                time.sleep(5)
                continue

            # Check the version of each node
            all_upgraded = True
            for node in nodes:
                node_version = self.get_node_version(node)
                if node_version is None:
                    # If the node is not reachable, consider it as not upgraded yet
                    all_upgraded = False
                    continue

                # Check if the node is upgraded to the target version
                if node_version != self.target_version:
                    self.log.info(f"Node {node['hostname']} is still on version {node_version}. Retrying...")
                    all_upgraded = False

            # If all nodes are upgraded, break the loop
            if all_upgraded:
                self.log.info("All nodes have been upgraded to the target version!")
                return True

            # If not all nodes are upgraded, wait and check again
            time.sleep(5)

        self.log.info(f"Timeout reached. Not all nodes are upgraded to {self.target_version} within {timeout} seconds.")
        return False

    def download_upload_pprof_s3(self):
        index_nodes = self.get_nodes_from_service_map()
        s3_pprof_links_list = []
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        for node in index_nodes:
            url = f'http://{node}:9102/debug/pprof/profile'
            response = requests.get(url, auth=HTTPBasicAuth(self.username, self.password))
            s3_file_name = f'pprof-{node}-{self.timestamp}'

            # Check if the request was successful
            if response.status_code == 200:
                # Write the response content to a file
                with open(s3_file_name, "wb") as file:
                    file.write(response.content)
                self.log.info(f"Profile data saved to {s3_file_name}")

                # Upload the file to S3

                public_url = f"https://{self.s3_bucket}.s3.amazonaws.com/{s3_file_name}"
                with open(s3_file_name, "rb") as file:
                    response = requests.put(url=public_url, data=file)
                if response.status_code == 200:
                    self.log.info(f"Public URL: {public_url}")
                    s3_pprof_links_list.append(public_url)
                else:
                    raise Exception("upload failed")

            else:
                raise Exception("download failed")

        return s3_pprof_links_list

    def cb_collect_logs(self):
        nodes = self.get_cluster_nodes()
        s3_link_regex = re.compile(r'(https?://[^\s]+)')
        s3_cbcollect_links = []
        timestamp = self.timestamp
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        for node in nodes:
            node_name = node['hostname'].split(':')[0]
            cbcollect_file_name = f'cbcollect-{timestamp}-{node_name}'
            command = f'/opt/couchbase/bin/cbcollect_info --upload-host=https://cb-engineering.s3.amazonaws.com --customer=\'{cbcollect_file_name}\' {cbcollect_file_name}'
            try:
                ssh_client.connect(node_name, 22, 'root', 'couchbase')
                # Execute the cbcollect_info command
                stdin, stdout, stderr = ssh_client.exec_command(command)

                # Read the command output
                output = stdout.read().decode()
                errors = stderr.read().decode()

                if errors:
                    self.log.info(f"Errors on {node['hostname']}:\n{errors}")

                # Extract the S3 link from the output
                match = s3_link_regex.search(output)
                if match:
                    s3_link = match.group(1)
                    s3_cbcollect_links.append(s3_link)
                    self.log.info(f"S3 link for {node['hostname']}: {s3_link}")
                else:
                    match = s3_link_regex.search(errors)
                    s3_link = match.group(1)
                    s3_cbcollect_links.append(s3_link)
                    self.log.info(f"S3 link for {node['hostname']}: {s3_link}")

            except Exception as e:
                self.log.info(f"An error occurred on {node['hostname']}: {e}")

            finally:
                # Close the SSH connection
                ssh_client.close()

        return s3_cbcollect_links

    def write_result_couchbase_bucket(self, result):
        result_bucket = self.result_cluster.bucket(self.result_bucket)
        result_collection = result_bucket.default_collection()

        # Insert the document into the result bucket
        doc_id = f"doc_{self.timestamp.split('.')[0]}"
        val = result
        try:
            result_collection.upsert(doc_id, val)
            self.log.info(
                f"Result successfully written to Couchbase bucket '{self.result_bucket}' with doc ID '{doc_id}'.")
        except Exception as e:
            self.log.error(f"Failed to write result to Couchbase bucket '{self.result_bucket}': {e}")

    def run_upgrade_workload(self):

        status = "FAIL"
        #step 1 run the workload before upgrade
        self.run_workload()

        #step 2 take a note of the stats like cpu and memory utilization before the upgrade starts
        stats_before = self.per_indexer_node_stats()

        #step 3 take a note of pprof files before upgrade
        pprof_file_list_before_upgrade = self.download_upload_pprof_s3()

        #step 4 wait for the upgrade to get over
        self.check_all_nodes_upgraded()

        #step 5 run the workload post upgrade
        self.run_workload()

        #step 6 take a note of the stats like cpu and memory utilization after the upgrade
        stats_after = self.per_indexer_node_stats()

        #step 7 take a note of pprof files after upgrade
        pprof_file_list_after_upgrade = self.download_upload_pprof_s3()

        #step 8 compare stats before and after upgrade
        diff_list = self.compare_indexer_stats(stats_before, stats_after)

        if len(diff_list) >= 1:
            cbcollect_list = self.cb_collect_logs()
        else:
            status = "PASS"
            cbcollect_list = []

        self.result = {
            "status": status,
            "pprof_before": pprof_file_list_before_upgrade,
            "pprof_after": pprof_file_list_after_upgrade,
            "cbcollect_info": cbcollect_list
        }

        self.log.info(json.dumps(self.result))

        #step 9 write the result to the result bucket
        self.write_result_couchbase_bucket(self.result)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--cluster_ip", help="Used to directly interact with the node")
    parser.add_argument("-r", "--result_cluster_ip", help="Node address to store the result")
    parser.add_argument('-u', '--username', help="Username of Cluster with data", default="Administrator")
    parser.add_argument('-p', '--password', help="Password of Cluster with data", default="password")
    parser.add_argument('-m', '--r_username', help="Username of Result Cluster", default="Administrator")
    parser.add_argument('-n', '--r_password', help="Password of Result Cluster", default="Password@123")
    parser.add_argument("-b", "--bucket", help="Used to directly interact with the node")
    parser.add_argument("-x", "--result_bucket", help="Used to directly interact with the node")
    parser.add_argument("-s", "--scope", help="Used to directly interact with the node")
    parser.add_argument("-mutation_timeout", "--mutation_timeout",
                        help="Used to set how long the mutataion must run for", default=10)
    parser.add_argument("-c", "--collection", help="Used to directly interact with the node")
    parser.add_argument("-select_queries", "--select_queries", help="Input the select scans", default="SELECT address FROM default:test_bucket_hotel._default._default WHERE country is not null and `type` is not null and (any r in reviews satisfies r.ratings.`Check in / front desk` is not null end), SELECT name FROM default:test_bucket_hotel._default._default WHERE country is not null")
    parser.add_argument("-s3_bucket", "--s3_bucket", help="input the bucket to which pprof must be uploaded")
    parser.add_argument("-s3_region", "--s3_region", help="s3 region for the pprof bucket")
    parser.add_argument("-s3_access_key", "--s3_access_key", help="s3 access_key for the pprof bucket")
    parser.add_argument("-s3_secret_key", "--s3_secret_key", help="s3 secret_key for the pprof bucket")
    parser.add_argument("-update_start", "--update_start", help="doc range start for update")
    parser.add_argument("-update_end", "--update_end", help="doc range end for update")
    parser.add_argument("-doc_template", "--doc_template", help="dataset type", default="Hotel")
    parser.add_argument("-ops", "--ops", help="ops rate for mutations", default=5000)
    parser.add_argument("-doc_size", "--doc_size", help="doc size value", default=500)
    parser.add_argument("-workers", "--workers", help="num workers", default=1)
    parser.add_argument("-target_version", "--target_version", help="the version to which the upgrade must be checked for", default="8.0.0")
    parser.add_argument("-diff_percent", "--diff_percent", help="max diff percent for which the cpu and mem utilization can be tolerated", default=20)

    args = parser.parse_args()
    cluster_ip = args.cluster_ip
    result_cluster_ip = args.result_cluster_ip
    bucket = args.bucket
    result_bucket = args.result_bucket
    scope = args.scope
    collection = args.collection
    username = args.username
    password = args.password
    r_username = args.r_username
    r_password = args.r_password
    update_start = args.update_start
    update_end = args.update_end
    select_queries = args.select_queries.split(",")
    s3_bucket = args.s3_bucket
    doc_template = args.doc_template
    ops = args.ops
    doc_size = args.doc_size
    workers = args.workers
    target_version = args.target_version
    diff_percent = int(args.diff_percent)


    val_obj = UpgradeWorkload(cluster_ip=cluster_ip, result_cluster_ip=result_cluster_ip,
                                    bucket=bucket, result_bucket=result_bucket,
                                    scope=scope, select_queries=select_queries, collection=collection,
                                    username=username, update_start=update_start, update_end=update_end,
                                    r_username=r_username, password=password, r_password=r_password, s3_bucket=s3_bucket, doc_template=doc_template, ops_rate=ops, doc_size=doc_size, workers=workers, target_version=target_version, diff_percent=diff_percent)
    val_obj.run_upgrade_workload()
    sys.exit(0 if not val_obj.result['cbcollect_info'] else 1)


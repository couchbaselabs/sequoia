import time
import logging
logging.basicConfig()
import requests
import json
import sys
import dns.resolver


class WaitForAllIndexBuildComplete:

    def __init__(self):
        if len(sys.argv) < 4:
            raise Exception("This script expects 3 arguments - index node ip, username, password")
        self.log = logging.getLogger(__file__)
        self.log.setLevel(logging.INFO)
        self.node_addr = sys.argv[1]
        self.cluster_username = sys.argv[2]
        self.cluster_password = sys.argv[3]
        self.excluded_buckets = []
        if len(sys.argv) > 4 and sys.argv[4] != "wait_for_index_ingestion":
            self.excluded_buckets = sys.argv[4].split(",")
        self.tls = False
        self.capella_run = False
        if "capella" in sys.argv:
            self.capella_run = True
        if "tls" in sys.argv:
            self.tls = True
        if self.tls or self.capella_run:
            self.node_port_index = '19102'
            self.port = '18091'
            self.scheme = "https"
            self.use_https = True
            if self.capella_run:
                self.rest_url = self.fetch_rest_url(self.node_addr)
                self.index_url = "{}://".format(self.scheme) + self.rest_url + ":" + self.node_port_index
                self.url = "{}://".format(self.scheme) + self.rest_url + ":" + self.port
                self.index_host_name = self.fetch_index_node_hostname(self.rest_url)
            else:
                self.index_host_name = self.fetch_index_node_hostname(self.node_addr)
                self.index_url = "{}://".format(self.scheme) + self.index_host_name + ":" + self.node_port_index
                self.url = "{}://".format(self.scheme) + self.node_addr + ":" + self.port
        else:
            self.node_port_index = '9102'
            self.port = '8091'
            self.scheme = "http"
            self.url = "{}://{}:{}".format(self.scheme, self.node_addr, self.port)
            self.index_host_name = self.fetch_index_node_hostname(self.node_addr)
            self.index_url = "{}://{}:{}".format(self.scheme, self.index_host_name, self.node_port_index)

        self.log.info("TLS flag:{} Capella run flag:{} arguments:{}".format(self.tls, self.capella_run, sys.argv))
        self.log.info("URL used for rest calls:{}".format(self.url))
        if len(sys.argv) < 4:
            raise Exception("This script expects 3 arguments - index node ip, username, password")

    def fetch_index_node_hostname(self, url):
        cluster_config_endpoint = "{}://{}:{}/pools/default".format(self.scheme, url, self.port)
        response = requests.get(cluster_config_endpoint, auth=(self.cluster_username, self.cluster_password),
                                verify=False)

        if response.ok:
            response = json.loads(response.content)
            for nodes in response['nodes']:
                if "index" in nodes['services']:
                    node_name = nodes['hostname'].split(":")[0]
                    return node_name
        else:
            response.raise_for_status()

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

    def check_index_status(self):
        response = self.get_index_status_metadata()
        excluded_buckets = self.excluded_buckets
        if "status" in response:
            # Check the status field for all indexes. status should be ready for all indexes.
            all_indexes_built = True

            for index in response["status"]:
                self.log.debug(index["name"] + "," + index["status"])
                if index["status"] == "Ready":
                    all_indexes_built &= True
                else:
                    if excluded_buckets :
                        if index["bucket"] not in excluded_buckets:
                            all_indexes_built &= False
                        else:
                            all_indexes_built &= True
                    else:
                        all_indexes_built &= False

            return all_indexes_built
        else:
            raise Exception("IndexStatus does not have status field")

    def get_index_status_metadata(self):
        index_status_endpoint = "{}/getIndexStatus".format(self.index_url)
        # Buckets to be skipped for checking build status
        # Get status for all indexes
        for i in range(5):
            try:
                response = requests.get(index_status_endpoint, auth=(self.cluster_username, self.cluster_password),
                                        verify=False)
            except:
                time.sleep(60)
        if response.ok:
            response = json.loads(response.content)
        else:
            response.raise_for_status()
        return response

    def check_indexes_not_ready(self):
        indexes_not_ready_list = list()
        response = self.get_index_status_metadata()
        excluded_buckets = self.excluded_buckets
        if "status" in response:
            # Check the status field for all indexes. status should be ready for all indexes.
            for index in response["status"]:
                if index["status"] != "Ready" and index["bucket"] not in excluded_buckets:
                    indexes_not_ready_list.append("{}.{}.{}.{}".format(index['bucket'],
                                                                       index['scope'], index['collection'],
                                                                       index['name']))
        else:
            raise Exception("IndexStatus does not have status field")
        return indexes_not_ready_list

    def check_index_pending(self, timeout=3600):
        index_node_list = []
        index_host_list = []
        cluster_config_endpoint = "{}/pools/default".format(self.url)
        index_status_endpoint = "{}/getIndexStatus".format(self.index_url)

        # Get status for all indexes
        response = requests.get(index_status_endpoint, auth=(self.cluster_username, self.cluster_password), verify=False)

        if response.ok:
            response = json.loads(response.content)
            # Find each indexer node that has indexes present
            if "status" in response:
                for index in response['status']:
                    for host in index['hosts']:
                        if host not in index_host_list:
                            host_name = host.split(":")[0]
                            index_host_list.append(host_name)
        else:
            response.raise_for_status()


        # Get list of indexer nodes
        response = requests.get(cluster_config_endpoint, auth=(self.cluster_username, self.cluster_password), verify=False)

        if response.ok:
            response = json.loads(response.content)
            for nodes in response['nodes']:
                if "index" in nodes['services']:
                    node_name = nodes['hostname'].split(":")[0]
                    # Add indexer nodes with indexes on them to list of nodes to be checked
                    if node_name in index_host_list:
                        index_node_list.append(node_name)
        else:
            response.raise_for_status()

        timedout = self.check_index_nodes(index_node_list,timeout)

        self.log.info ("Sleep for 120 seconds to see if indexes are fully done being built")
        # Sleep for some time and then again make sure that there are no docs_pending in any indexes
        if not timedout:
            time.sleep(120)
        else:
            raise Exception("Timeout has been reached and ingestion has not completed!")

        timedout = self.check_index_nodes(index_node_list,timeout)

        if timedout:
            raise Exception("Timeout has been reached and ingestion has not completed!")

        return all_indexes_caught_up

    def check_index_nodes(self, index_node_list = [], timeout=3600):
        timedout = False
        st_time = time.time()
        for index_node in index_node_list:
            all_indexes_caught_up = False
            if timedout:
                raise Exception("Timeout has been reached and ingestion has not completed!")
            index_stats = {}
            index_stats_endpoint = "{}/stats".format(self.index_url)
            while not all_indexes_caught_up:
                # Get status for all indexes
                response = requests.get(index_stats_endpoint, auth=(self.cluster_username, self.cluster_password), verify=False)

                if response.ok:
                    response = json.loads(response.content)
                    for item in response:
                        if "num_docs_pending" in item:
                            if response[item] == 0:
                                index_stats[item] = True
                            else:
                                index_stats[item] = False
                else:
                    response.raise_for_status()
                    break

                if st_time + timeout < time.time():
                    timedout = True
                    break

                for key in index_stats.keys():
                    if index_stats[key]:
                        all_indexes_caught_up = True
                    else:
                        all_indexes_caught_up = False
        return timedout

if __name__ == '__main__':
    all_indexes_built = False
    check_index_stats = False
    all_indexes_caught_up = False
    hard_all_index_built_timeout = 43200
    index_obj = WaitForAllIndexBuildComplete()
    capella_run = False
    if len(sys.argv) > 4:
        if sys.argv[4] == "wait_for_index_ingestion":
            check_index_stats = True
    if check_index_stats:
        try:
            if len(sys.argv) < 6:
                raise Exception("This script expects 5 arguments - index node ip, username, password, wait_for_index_ingestion, timeout")
            else:
                try:
                    timeout = int(sys.argv[5])
                except:
                    timeout = int(sys.argv[6])
                all_indexes_caught_up = index_obj.check_index_pending(timeout)
        except Exception as e:
            print("Error while waiting for ingestion")
            print(str(e))
    else:
        cr_time = time.time()
        while (not all_indexes_built) and (cr_time +
                                           hard_all_index_built_timeout > time.time()):
            try:
                all_indexes_built = index_obj.check_index_status()
            except Exception as e:
                print(str(e))
                print("Error getting index status")
                break

            # Sleep for 1 min
            time.sleep(60)
    if not all_indexes_built:
        index_list = index_obj.check_indexes_not_ready()
        raise Exception("All indexes were not built after {} seconds. Indexes not built {}".format(hard_all_index_built_timeout, index_list))

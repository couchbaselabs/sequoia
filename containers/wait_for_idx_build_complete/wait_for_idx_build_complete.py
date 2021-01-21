import time

import requests
import json
import sys


class WaitForAllIndexBuildComplete():
    def check_index_status(self):
        if len(sys.argv) < 4:
            raise Exception("This script expects 3 arguments - index node ip, username, password")

        index_status_endpoint = "http://" + sys.argv[1] + ":9102/getIndexStatus"
        cluster_username = sys.argv[2]
        cluster_password = sys.argv[3]
        # Buckets to be skipped for checking build status
        excluded_buckets = []
        if sys.argv[4]:
            excluded_buckets = sys.argv[4].split(",")


        # Get status for all indexes
        response = requests.get(index_status_endpoint, auth=(cluster_username, cluster_password), verify=True)

        if response.ok:
            response = json.loads(response.content)

            if "status" in response:
                all_indexes_built = True
                # Check the status field for all indexes. status should be ready for all indexes.
                for index in response["status"]:
                    if (index["bucket"] not in excluded_buckets):
                        if index["status"] != "Ready":
                            all_indexes_built &= False
                        else:
                            all_indexes_built &= True
                    else:
                        pass

                return all_indexes_built
            else:
                raise Exception("IndexStatus does not have status field")
        else:
            response.raise_for_status()

    def check_index_pending(self, timeout=3600):
        index_node_list = []
        index_host_list = []
        cluster_config_endpoint = "http://" + sys.argv[1] + ":8091/pools/default"
        cluster_username = sys.argv[2]
        cluster_password = sys.argv[3]

        index_status_endpoint = "http://" + sys.argv[1] + ":9102/getIndexStatus"

        # Get status for all indexes
        response = requests.get(index_status_endpoint, auth=(cluster_username, cluster_password), verify=True)

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
        response = requests.get(cluster_config_endpoint, auth=(cluster_username, cluster_password), verify=True)

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

        print "Sleep for 120 seconds to see if indexes are fully done being built"
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
        cluster_username = sys.argv[2]
        cluster_password = sys.argv[3]
        for index_node in index_node_list:
            all_indexes_caught_up = False
            if timedout:
                raise Exception("Timeout has been reached and ingestion has not completed!")
            index_stats = {}
            index_stats_endpoint = "http://" + index_node + ":9102/stats"
            while not all_indexes_caught_up:
                # Get status for all indexes
                response = requests.get(index_stats_endpoint, auth=(cluster_username, cluster_password), verify=True)

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
    if len(sys.argv) > 4:
        if sys.argv[4] == "wait_for_index_ingestion":
            check_index_stats = True
    if check_index_stats:
        try:
            if len(sys.argv) != 6:
                raise Exception("This script expects 5 arguments - index node ip, username, password, wait_for_index_ingestion, timeout")
            else:
                all_indexes_caught_up = WaitForAllIndexBuildComplete().check_index_pending(int(sys.argv[5]))
        except Exception as e:
            print "Error while waiting for ingestion"
            print str(e)
    else:
        while not all_indexes_built:
            try:
                all_indexes_built = WaitForAllIndexBuildComplete().check_index_status()
            except Exception as e:
                print "Error getting index status"
                break

            # Sleep for 1 min
            time.sleep(60)


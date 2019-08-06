import time

import requests
import json
import sys


class WaitForAllIndexBuildComplete():
    def check_index_status(self):

        if len(sys.argv) != 4:
            raise Exception("This script expects 3 arguments - index node ip, username, password")

        index_status_endpoint = "http://" + sys.argv[1] + ":9102/getIndexStatus"
        cluster_username = sys.argv[2]
        cluster_password = sys.argv[3]

        # Get status for all indexes
        response = requests.get(index_status_endpoint, auth=(cluster_username, cluster_password), verify=True)

        if response.ok:
            response = json.loads(response.content)

            if "status" in response:
                all_indexes_built = True
                # Check the status field for all indexes. status should be ready for all indexes.
                for index in response["status"]:
                    if index["status"] != "Ready":
                        all_indexes_built &= False
                    else:
                        all_indexes_built &= True
                return all_indexes_built
            else:
                raise Exception("IndexStatus does not have status field")
        else:
            response.raise_for_status()


if __name__ == '__main__':
    all_indexes_built = False
    while not all_indexes_built:
        try:
            all_indexes_built = WaitForAllIndexBuildComplete().check_index_status()
        except Exception as e:
            print "Error getting index status"
            break

        # Sleep for 1 min
        time.sleep(60)


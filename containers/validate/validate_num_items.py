import requests
import json
import sys


class Validation():
    def run(self):

        if len(sys.argv) != 7:
            raise Exception("This script expects 7 arguments")

        src_num_items = 0
        dest_num_items = 0

        src_cluster_url = "http://" + sys.argv[1] + "/nodes/self"
        src_cluster_username = sys.argv[2]
        src_cluster_password = sys.argv[3]

        dest_cluster_url = "http://" + sys.argv[4] + "/nodes/self"
        dest_cluster_username = sys.argv[5]
        dest_cluster_password = sys.argv[6]

        # Get No. of items on Source cluster
        src_response = requests.get(src_cluster_url, auth=(
        src_cluster_username, src_cluster_password), verify=True)

        if (src_response.ok):
            src_response = json.loads(src_response.content)
            if "interestingStats" in src_response:
                if "curr_items_tot" in src_response["interestingStats"]:
                    src_num_items = src_response["interestingStats"][
                        "curr_items_tot"]
                else:
                    raise Exception("Stats do not have curr_items_tot")
            else:
                raise Exception("Stats do not have interestingStats")
        else:
            src_response.raise_for_status()

        # Get No. of items on Destination cluster
        dest_response = requests.get(dest_cluster_url, auth=(
        dest_cluster_username, dest_cluster_password), verify=True)

        if (dest_response.ok):
            dest_response = json.loads(dest_response.content)
            if "interestingStats" in dest_response:
                if "curr_items_tot" in dest_response["interestingStats"]:
                    dest_num_items = dest_response["interestingStats"][
                        "curr_items_tot"]
                else:
                    raise Exception("Stats do not have curr_items_tot")
            else:
                raise Exception("Stats do not have interestingStats")
        else:
            dest_response.raise_for_status()

        if src_num_items != dest_num_items:
            raise AssertionError(
                "Validation failed. No. of items mismatch in source and destination cluster. # Items on src = %s, # Items on dest = %s" % (
                src_num_items, dest_num_items))
        else:
            print ("All ok. # Items on src = {0}, # Items on dest = {1}".format(
                src_num_items, dest_num_items))


if __name__ == '__main__':
    Validation().run()

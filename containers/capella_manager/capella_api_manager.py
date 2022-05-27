import argparse
import json
import time
import sys
import os
import logging
import random

from CapellaAPI import CapellaAPI

NODES_MAX = 8

logging.basicConfig()


class APIManager:
    def __init__(self, url="https://cloudapi.cloud.couchbase.com"):
        self.log = logging.getLogger("capella_api_manager")
        self.parser = argparse.ArgumentParser()
        self.parser.add_argument("-u", "--username", help="Capella username", required=True)
        self.parser.add_argument("-p", "--password", help="Capella login password", required=True)
        self.parser.add_argument("-s", "--secret", help="API secret key", required=True)
        self.parser.add_argument("-a", "--access", help="API access key", required=True)
        self.parser.add_argument("-c", "--cluster", help="Cluster Name", default="system_testing")
        self.parser.add_argument("-o", "--operation", help="Operations to be run.", default="get_cluster_id")
        self.parser.add_argument("-n", "--numnodes", help="Node count used for scaling operations", default=1)
        self.parser.add_argument("-l", "--log_level", help="Log levels: DEBUG/INFO/ERROR", default="INFO")
        self.parser.add_argument("-b", "--bucket", help="Bucket to be created/deleted", default="test")
        self.parser.add_argument("-d", "--db_user", help="DB username", default="Administrator")
        self.parser.add_argument("-e", "--db_password", help="DB password", default="Password1!")
        self.parser.add_argument("-w", "--project", help="Project name if it already exists", default="system_testing")
        self.parser.add_argument("-j", "--json", help="Cluster config to be used for deployment")
        self.args = self.parser.parse_args()
        self.log_level = logging.INFO
        if self.args.log_level == 'DEBUG':
            self.log_level = logging.DEBUG
        elif self.args.log_level == 'ERROR':
            self.log_level = logging.ERROR
        self.log.setLevel(self.log_level)
        self.log.debug("Parsed arguments are {}".format(self.args))
        self.secret = self.args.secret
        self.access = self.args.access
        self.operation = self.args.operation
        self.username = self.args.username
        self.password = self.args.password
        self.db_user = self.args.db_user
        self.db_password = self.args.db_password
        self.cluster_config = self.args.json
        self.url = url
        self.node_count = int(self.args.numnodes)
        self.bucket_name = self.args.bucket
        self.api_obj = CapellaAPI(url=self.url, secret=self.secret, access=self.access, user=self.username,
                                  pwd=self.password)
        self.cluster_name = self.args.cluster
        self.project_name = self.args.project
        if self.cluster_config is None:
            with open(os.path.join(os.path.dirname(__file__), 'cluster_config.json')) as f:
                self.cluster_config = json.load(f)
        self.log.debug("Cluster config json content is {}".format(self.cluster_config))

    def get_cluster_id(self, name):
        return self._get_meta_data(name=name)['id']

    def _get_meta_data(self, name):
        all_clusters = json.loads(self.api_obj.get_clusters().content)['data']
        self.log.debug("All clusters: {}".format(all_clusters))
        for cluster in all_clusters['items']:
            if cluster['name'] == name:
                return cluster

    def get_tenant_id(self):
        self.log.debug("Fetching tenant ID")
        return json.loads(self.api_obj.get_clusters().content)['data']['tenantId']

    def get_project_id(self, name):
        self.log.debug("Fetching project ID")
        return self._get_meta_data(name=name)['projectId']

    def get_bucket_id(self, name):
        self.log.debug("Fetching bucket ID")
        tenant_id, project_id, cluster_id = self.get_tenant_id(), self.get_project_id(
            self.project_name), self.get_cluster_id(self.cluster_name)
        resp = self.api_obj.get_buckets(tenant_id, project_id, cluster_id)
        if resp.status_code != 200:
            raise Exception("Response when trying to fetch buckets.")
        buckets = json.loads(resp.content)['buckets']['data']
        for bucket in buckets:
            if bucket['data']['name'] == name:
                return bucket['data']['id']

    def get_db_users(self, name):
        self.log.debug("Fetching user ID")
        tenant_id, project_id, cluster_id = self.get_tenant_id(), self.get_project_id(
            self.project_name), self.get_cluster_id(self.cluster_name)
        resp = self.api_obj.get_db_users(tenant_id, project_id, cluster_id)
        if resp.status_code != 200:
            raise Exception("Response when trying to fetch users.")
        users = json.loads(resp.content)['data']
        for user in users:
            if user['data']['name'] == name:
                return user['data']['id']

    def get_num_nodes(self):
        tenant_id = self.get_tenant_id()
        project_id = self.get_project_id(self.project_name)
        cluster_id = self.get_cluster_id(self.cluster_name)
        all_nodes = json.loads(self.api_obj.get_nodes(tenant_id, project_id, cluster_id).content)['data']
        return len(all_nodes)

    def create_bucket(self, bucket_config=None, bucket_name="test", backup_config=None):
        tenant_id, project_id, cluster_id = self.get_tenant_id(), self.get_project_id(
            self.project_name), self.get_cluster_id(self.cluster_name)
        self.log.debug("Tenant ID: {}, Project ID: {} ClusterID: {}. bucket name {}".format(tenant_id, project_id,
                                                                                            cluster_id,
                                                                                            bucket_name))
        if not bucket_config:
            bucket_config = {
                "name": bucket_name,
                "bucketConflictResolution": "seqno",
                "memoryAllocationInMb": 100,
                "flush": False,
                "replicas": 1,
                "durabilityLevel": "none",
                "timeToLive": None
            }
        if not backup_config:
            bucket_config['backupSchedule'] = {"day": 0, "hour": 0,
                                               "incrementalInterval": {"value": 1, "unit": "daily"},
                                               "fullInterval": "weekly", "retentionTime": "90days"}
        else:
            bucket_config['backupSchedule'] = backup_config
        resp = self.api_obj.create_bucket(tenant_id, project_id, cluster_id, bucket_config)
        self.log.info("Create Bucket status:{}".format(resp.status_code))

    def delete_bucket(self, name):
        tenant_id, project_id, cluster_id = self.get_tenant_id(), self.get_project_id(
            self.project_name), self.get_cluster_id(self.cluster_name)
        self.log.debug("Tenant ID: {}, Project ID: {} ClusterID: {}".format(tenant_id, project_id, cluster_id))
        bucket_id = self.get_bucket_id(name)
        self.log.debug("Bucket ID to be deleted : {}".format(bucket_id))
        resp = self.api_obj.delete_bucket(tenant_id, project_id, cluster_id, bucket_id)
        self.log.info("Delete Bucket status:{}".format(resp.status_code))

    def scale_up(self, node_count, timeout=60):
        self.log.info("Will scale the cluster by {} node/s".format(node_count))
        total_nodes = self.get_num_nodes() + node_count
        self._scale(node_count=total_nodes, timeout=timeout)

    def scale_down(self, node_count=3, timeout=60):
        self.log.info("Will scale down the cluster to {} node/s".format(node_count))
        self._scale(node_count=node_count, timeout=timeout)

    def _scale(self, node_count, timeout=60):
        self.log.debug("In _scale method")
        all_services_list = ["data", "index", "query", "search", "analytics"]
        new_server_service_configuration = {
            "servers": [
                {
                    "compute": "r5.xlarge",
                    "size": node_count,
                    "services": all_services_list,
                    "storage": {
                        "size": 50,
                        "IOPS": 3000,
                        "type": "GP3"
                    }
                }
            ]
        }
        cluster_id = self.get_cluster_id(name=self.cluster_name)
        self.log.debug(
            "Custom cluster config used: {}. Cluster ID: {}".format(new_server_service_configuration, cluster_id))
        resp = self.api_obj.update_cluster_servers(cluster_id=cluster_id,
                                                   new_cluster_server_configuration=new_server_service_configuration)
        self.log.info("Update cluster config response: {}".format(resp.content))
        time.sleep(30)
        cluster_status = self.get_cluster_status()
        time_now = time.time()
        self.log.info("Cluster status is {}".format(cluster_status))
        while cluster_status == 'scaling' and time.time() - time_now < timeout * 60:
            cluster_status = self.get_cluster_status()
            if cluster_status == 'healthy':
                break
            time.sleep(20)
            self.log.info("Cluster status is {}".format(cluster_status))
        cluster_status = self.get_cluster_status()
        self.log.info("Cluster status after scale up/down: {}".format(cluster_status))
        if cluster_status != 'healthy':
            self.log.error("Scale down operation ended in error. Cluster status is not healthy")
            raise Exception("Scale down operation failure")

    def get_cluster_status(self, cluster_name=None):
        if cluster_name is None:
            cluster_name = self.cluster_name
        cluster_id = self.get_cluster_id(name=cluster_name)
        cluster_status = json.loads(self.api_obj.get_cluster_status(cluster_id=cluster_id).content)
        return cluster_status['status']

    def create_db_user(self, username, password):
        tenant_id, project_id, cluster_id = self.get_tenant_id(), self.get_project_id(
            self.project_name), self.get_cluster_id(self.cluster_name)
        self.log.debug("Tenant ID: {}, Project ID: {} ClusterID: {}".format(tenant_id, project_id, cluster_id))
        resp = self.api_obj.create_db_user(tenant_id, project_id, cluster_id, username, password)
        self.log.info("create_db_user status:{}".format(resp.status_code))

    def delete_db_user(self, username):
        tenant_id, project_id, cluster_id = self.get_tenant_id(), self.get_project_id(
            self.project_name), self.get_cluster_id(self.cluster_name)
        self.log.debug("Tenant ID: {}, Project ID: {} ClusterID: {}".format(tenant_id, project_id, cluster_id))
        user_id = self.get_db_users(username)
        self.log.debug("User ID to be deleted : {}".format(user_id))
        resp = self.api_obj.delete_db_user(tenant_id, project_id, cluster_id, user_id)
        self.log.info("Delete user status:{}".format(resp.status_code))

    def create_cluster(self, project_name, cluster_name, timeout=30):
        self.log.info("Will create the cluster {} on project {}".format(cluster_name, project_name))
        project_id = self.get_project_id(project_name)
        self.log.info("Project ID:{}".format(project_id))
        if project_id is None:
            raise Exception(
                "Project with the name {} not found. Will not proceed with cluster creation".format(project_name))
        cluster_configuration = self.cluster_config
        cluster_configuration["clusterName"] = cluster_name
        cluster_configuration["projectId"] = project_id
        self.log.info("Payload used for cluster creation:{}".format(cluster_configuration))
        resp = self.api_obj.create_cluster(cluster_configuration)
        self.log.info("Create cluster config response: {}".format(resp.content))
        time.sleep(30)
        cluster_status = self.get_cluster_status(cluster_name)
        time_now = time.time()
        self.log.info("Cluster status is {}".format(cluster_status))
        while cluster_status == 'deploying' and time.time() - time_now < timeout * 60:
            cluster_status = self.get_cluster_status(cluster_name)
            if cluster_status == 'healthy':
                break
            time.sleep(20)
            self.log.info("Cluster status is {}".format(cluster_status))
        cluster_status = self.get_cluster_status(cluster_name)
        self.log.info("Cluster status after creation: {}".format(cluster_status))
        if cluster_status != 'healthy':
            self.log.error("Create cluster operation ended in error. Cluster status is not healthy")
            raise Exception("Create cluster operation failure")

    def delete_cluster(self, cluster_name, timeout=20):
        self.log.info("Will delete the cluster {}".format(cluster_name))
        cluster_id = self.get_cluster_id(cluster_name)
        self.log.info("Cluster ID to be deleted".format(cluster_id))
        if cluster_id is None:
            raise Exception(
                "Cluster with the name {} not found. Will not proceed with cluster deletion".format(cluster_name))
        self.api_obj.delete_cluster(cluster_id)
        time.sleep(30)
        cluster_status = self.get_cluster_status(cluster_name)
        self.log.info("Cluster status is {}".format(cluster_status))
        time_now = time.time()
        while cluster_status == 'destroying' and time.time() - time_now < timeout * 60:
            try:
                cluster_status = self.get_cluster_status(cluster_name)
            except:
                break
            time.sleep(20)
            self.log.info("Cluster status is {}".format(cluster_status))

    def allow_my_ip(self):
        tenant_id, project_id, cluster_id = self.get_tenant_id(), self.get_project_id(
            self.project_name), self.get_cluster_id(self.cluster_name)
        self.log.info("Will add IP to allow list for tenant ID {} project ID {} cluster ID {}".format(tenant_id,
                                                                                                      project_id,
                                                                                                      cluster_id))
        resp = self.api_obj.allow_my_ip(tenant_id, project_id, cluster_id)
        self.log.info("Add allowed ip response: {}".format(resp.status_code))

    def get_srv_domain(self):
        tenant_id, project_id, cluster_id = self.get_tenant_id(), self.get_project_id(
            self.project_name), self.get_cluster_id(self.cluster_name)
        resp_json = json.loads(self.api_obj.get_cluster_internal(tenant_id, project_id, cluster_id).content)
        srv_domain = resp_json['data']['connect']['srv']
        self.log.info(
            "SRV domain is : {} for cluster : {} project : {}".format(srv_domain, self.cluster_name, self.project_name))
        return srv_domain

    def populate_provider_file(self, file_path='/tmp/provider_temp.yml'):
        srv_domain = self.get_srv_domain()
        file_content = "---\n"
        for i in range(self.get_num_nodes()):
            file_content += "{}\n".format(srv_domain)
        print("File content is {}".format(file_content))
        with open(file_path, 'w+') as f:
            f.write(file_content)

    def restore_from_backup(self, timeout=20):
        self.api_obj.restore_from_backup(cluster_name=self.cluster_name, project_name=self.project_name,
                                         bucket_name=self.bucket_name)
        tenant_id, project_id, cluster_id = self.get_tenant_id(), self.get_project_id(
            self.project_name), self.get_cluster_id(name=self.cluster_name)
        time.sleep(120)
        time_now = time.time()
        while time.time() - time_now < timeout * 60:
            jobs_response = self.api_obj.jobs(project_id=project_id, tenant_id=tenant_id, cluster_id=cluster_id).content
            self.log.debug(f"resp_json is {jobs_response}")
            resp_json_data = json.loads(str(jobs_response, "UTF-8"))['data']
            if not resp_json_data:
                break
            else:
                self.log.debug(f"resp_json_data is {resp_json_data}")
                for item in resp_json_data:
                    if item['data']['jobType'] == 'restore' and item['data']['completionPercentage'] < 100:
                        time.sleep(60)

    def backup_now(self, timeout=20):
        self.api_obj.backup_now(cluster_name=self.cluster_name, project_name=self.project_name,
                                bucket_name=self.bucket_name)
        tenant_id, project_id, cluster_id = self.get_tenant_id(), self.get_project_id(
            self.project_name), self.get_cluster_id(name=self.cluster_name)
        time.sleep(120)
        time_now = time.time()
        while time.time() - time_now < timeout * 60:
            jobs_response = self.api_obj.jobs(project_id=project_id, tenant_id=tenant_id, cluster_id=cluster_id).content
            self.log.debug(f"resp_json is {jobs_response}")
            resp_json_data = json.loads(str(jobs_response, "UTF-8"))['data']
            if not resp_json_data:
                break
            else:
                self.log.debug(f"resp_json_data is {resp_json_data}")
                for item in resp_json_data:
                    if item['data']['jobType'] == 'backup' and item['data']['completionPercentage'] < 100:
                        time.sleep(60)

    def run(self):
        if self.operation == 'get_cluster_id':
            self.log.info("Cluster ID: {}".format(self.get_cluster_id(self.cluster_name)))
        elif self.operation == 'get_cluster_status':
            self.log.info("Cluster status: {}".format(self.get_cluster_status()))
        elif self.operation == 'scale_up':
            self.scale_up(node_count=self.node_count)
        elif self.operation == 'scale_down':
            self.scale_down(node_count=3)
        elif self.operation == 'get_num_nodes':
            self.log.info("Number of nodes :{}".format(self.get_num_nodes()))
        elif self.operation == 'create_bucket':
            self.create_bucket(bucket_name=self.bucket_name)
        elif self.operation == 'delete_bucket':
            self.delete_bucket(self.bucket_name)
        elif self.operation == 'create_db_user':
            self.create_db_user(self.db_user, self.db_password)
        elif self.operation == 'delete_db_user':
            self.delete_db_user(self.db_user)
        elif self.operation == 'create_cluster':
            self.create_cluster(project_name=self.project_name, cluster_name=self.cluster_name)
        elif self.operation == 'delete_cluster':
            self.delete_cluster(self.cluster_name)
        elif self.operation == 'allow_my_ip':
            self.allow_my_ip()
        elif self.operation == 'get_srv_domain':
            self.get_srv_domain()
        elif self.operation == 'populate_provider_file':
            self.populate_provider_file()
        elif self.operation == 'backup_now':
            self.backup_now()
        elif self.operation == 'restore_from_backup':
            self.restore_from_backup()
        else:
            raise Exception("Incorrect choice. Choices can be :"
                            "get_cluster_id, get_cluster_status, scale_up, scale_down, get_num_nodes, create_bucket, "
                            "delete_bucket, create_db_user, delete_db_user, create_cluster, delete_cluster,"
                            "allow_my_ip, get_srv_domain, populate_provider_file, backup_now, restore_from_backup")


if __name__ == "__main__":
    api_obj = APIManager()
    api_obj.run()
    print("Capella Manager operations complete")

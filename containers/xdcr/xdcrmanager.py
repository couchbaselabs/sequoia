import subprocess
import threading
import random
import time
import argparse


class Command(object):
    def __init__(self, cmd, debug):
        self.cmd = cmd
        self.process = None
        self.ret = []
        self.start = 0
        self.end = 0
        self.debug = debug

    def run(self, timeout):
        def target():
            if self.debug:
                print("Executing cmd " + self.cmd)
            self.start = time.time()
            self.process = subprocess.Popen(self.cmd, shell=True,
                                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.ret = self.process.communicate()[0].split(b'\n')

        thread = threading.Thread(target=target)
        thread.start()
        thread.join(timeout)
        self.end = time.time()
        try:
            if thread.is_alive():
                if self.debug:
                    print("Terminating process after {0}s".format(int(self.end - self.start)))
                self.process.terminate()
        except Exception as e:
            if self.debug:
                print("Unable to terminate process {0}".format(e.message))

        thread.join()
        return self.ret


class XDCRManager:

    def __init__(self):
        self.settings = {"checkpointInterval": range(60, 14400, 100),
                         "compressionType": ["Auto"],
                         "desiredLatency": range(100, 10000, 100),
                         "docBatchSizeKb": range(10, 10000, 100),
                         "failureRestartInterval": range(1, 300, 10),
                         "filterExpression": ["REGEXP_CONTAINS(META().id,'0$')"],
                         "filterSkipRestream": [True, False],
                         "filterVersion": [0, 1],
                         "goMaxProcs": range(1, 100, 1),
                         "logLevel": ["Info", "Debug"],
                         "networkUsageLimit": range(0, 1000000, 100),
                         "optimisticReplicationThreshold": range(0, 20 * 1024 * 1024, 1024),
                         "pauseRequested": [True, False],
                         "priority": ["High", "Medium", "Low"],
                         "sourceNozzlePerNode": range(1, 100, 10),
                         "statsInterval": range(200, 600000, 100),
                         "targetNozzlePerNode": range(1, 100, 10),
                         "type": ["xmem", "continuous"],
                         "workerBatchSize": range(500, 10000, 100),
                         "collectionsExplicitMapping": [True, False],
                         "colMappingRules": {},
                         "collectionsMigrationMode": [True, False]
                         }
        self.actions = ["create_replication", "delete_replication", "change_setting",
                        "flush_bucket", "flush_all_buckets",
                        "cleanup", "validate"]
        self.args = self.parseargs()
        self.node_rep_map = {}
        self.node_bkt_map = {}
        self.nodes = {}
        self.populate_nodes()
        self.dispatch()

    def parseargs(self):
        parser = argparse.ArgumentParser()
        # Clusters
        parser.add_argument("-n", "--node", help="Source Cluster Node IP")
        parser.add_argument("-o", "--port", help="Source Cluster Node Port", default="8091")
        parser.add_argument("-u", "--username", help="Source Cluster Username", default="Administrator")
        parser.add_argument("-p", "--password", help="Source Cluster Password", default="password")
        parser.add_argument("-rn", "--remote_node", help="Remote Cluster Node IP")
        parser.add_argument("-ro", "--remote_port", help="Remote Cluster Node Port", default="8091")
        parser.add_argument("-ru", "--remote_username", help="Remote Cluster Username", default="Administrator")
        parser.add_argument("-rp", "--remote_password", help="Remote Cluster Password", default="password")

        # Action
        parser.add_argument("-a", "--action", choices=self.actions,
                            help="Choose an action to be performed", default="create_replication")
        parser.add_argument("-l", "--loop", type=bool, help="loop forever if true", default=False)

        # Replication details
        parser.add_argument("-b", "--bucket", help="Source bucket name")
        parser.add_argument("-rb", "--remote_bucket", help="Remote bucket name")
        parser.add_argument("-replid", "--replication_id", help="Replication Id")
        parser.add_argument("-s", "--replication_setting", help="Replication setting")
        parser.add_argument("-v", "--replication_setting_value", help="Replication setting value")

        # debug mode
        parser.add_argument("-d", "--debug", type=bool, help="enable debug prints", default=False)

        return parser.parse_args()

    def populate_nodes(self):
        self.nodes[self.args.node] = {"username": self.args.username,
                                      "password": self.args.password,
                                      "port": self.args.port}
        if self.args.remote_node:
            self.nodes[self.args.remote_node] = {"username": self.args.remote_username,
                                                 "password": self.args.remote_password,
                                                 "port": self.args.remote_port}

    def dispatch(self):
        if self.args.loop:
            src = self.args.node
            remote = self.args.remote_node
            self.refresh_maps(src)
            self.refresh_maps(remote)
            src_bkt = random.choice(self.node_bkt_map[src])
            remote_bkt = random.choice(self.node_bkt_map[remote])
            self.create_replication(src, remote, src_bkt, remote_bkt)
            self.create_replication(remote, src, remote_bkt, src_bkt)
            while (1):
                self.random_dispatch()
                dispatch_interval = random.randint(10, 60)
                time.sleep(dispatch_interval)
                if self.args.debug:
                    print("Sleeping {}s between loops".format(dispatch_interval))
        else:
            self.regular_dispatch()

    def random_dispatch(self):
        action = random.choice(self.actions)
        src = random.choice(list(self.nodes.keys()))
        remote = random.choice(list(self.nodes.keys()))
        node = random.choice([src, remote])
        self.refresh_maps(src)
        self.refresh_maps(remote)
        setting = random.choice(list(self.settings.keys()))
        val = random.choice(self.settings[setting])

        if action == "create_replication":
            src_bkt = random.choice(self.node_bkt_map[src])
            remote_bkt = random.choice(self.node_bkt_map[remote])
            self.create_replication(src, remote, src_bkt, remote_bkt)
        elif action == "delete_replication":
            if len(self.node_rep_map[node]):
                rep = random.choice(self.node_rep_map[node])
                self.delete_replication(src, rep)
        elif action == "change_setting":
            if len(self.node_rep_map[node]):
                rep = random.choice(self.node_rep_map[node])
                self.change_setting(node, rep, setting, val)
        elif action == "flush_bucket":
            self.flush_bucket(node, self._random_bucket(node))
        elif action == "flush_all_buckets":
            self.flush_all_buckets(node)
        elif action == "create_collections":
            self.delete_bucket(node, self._random_bucket(node))
        elif action == "delete_all_buckets":
            self.delete_all_buckets(node)
        elif action == "cleanup":
            pass
        elif action == "validate":
            pass

    def regular_dispatch(self):
        action = self.args.action
        src = self.args.node
        if self.args.remote_node:
            remote = self.args.remote_node
        if self.args.replication_id:
            rep = self.args.replication_id
        if self.args.bucket:
            src_bkt = self.args.bucket
        if self.args.remote_bucket:
            remote_bkt = self.args.remote_bucket
        if self.args.replication_setting:
            setting = self.args.replication_setting
        if self.args.replication_setting_value:
            val = self.args.replication_setting_value

        if action == "create_replication":
            self.create_replication(src, remote, src_bkt, remote_bkt)
        elif action == "delete_replication":
            self.delete_replication(src, rep)
        elif action == "change_setting":
            self.change_setting(src, rep, setting, val)
        elif action == "flush_all_buckets":
            self.flush_all_buckets(src)
            self.flush_all_buckets(remote)
        elif action == "delete_all_buckets":
            self.delete_all_buckets(src)
            self.delete_all_buckets(remote)
        elif action == "cleanup":
            pass
        elif action == "validate":
            pass

    def execute_cmd(self, cmd, timeout=60):
        command = Command(cmd, self.args.debug)
        return command.run(timeout=timeout)

    def refresh_maps(self, node_ip, add_repl=None, drop_repl=None):
        if add_repl:
            if node_ip in self.node_rep_map.keys():
                if add_repl not in self.node_rep_map[node_ip]:
                    self.node_rep_map[node_ip].append(add_repl)
            else:
                self.node_rep_map[node_ip] = [add_repl]
        if drop_repl:
            if node_ip in self.node_rep_map.keys():
                if drop_repl in self.node_rep_map[node_ip]:
                    self.node_rep_map[node_ip].remove(drop_repl)
        node = self.nodes[node_ip]
        out = self.execute_cmd(
            "curl -u " + node["username"] + ':' + node["password"] + " http://" + node_ip + ':' + node["port"] +
            "/pools/default/buckets/")
        lines = str(out).split('"name":"')
        bkts = []
        for line in range(1, len(lines)):
            bkts.append(lines[line].split('","')[0])
        self.node_bkt_map[node_ip] = bkts
        if self.args.debug:
            print("node_rep_map:{}".format(self.node_rep_map))
            print("node_bkt_map:{}".format(self.node_bkt_map))

    def _random_bucket(self, node_ip):
        if node_ip in self.node_bkt_map.keys():
            bucket = random.choice(self.node_bkt_map[node_ip])
            return bucket
        return "default"

    def flush_bucket(self, node_ip, bucket):
        node = self.nodes[node_ip]
        self.execute_cmd(
            "curl -X POST -u " + node["username"] + ':' + node["password"] + " http://" + node_ip + ':' + node["port"] +
            "/pools/default/buckets/" + bucket + "/controller/doFlush")

    def flush_all_buckets(self, node_ip):
        for bucket in self.node_bkt_map[node_ip]:
            self.flush_bucket(node_ip, bucket)

    def delete_bucket(self, node_ip, bucket):
        node = self.nodes[node_ip]
        self.execute_cmd(
            "curl -X DELETE -u " + node["username"] + ':' + node["password"] + " http://" + node_ip + ':' + node[
                "port"] +
            "/pools/default/buckets/" + bucket)
        self.refresh_maps(node_ip)

    def delete_all_buckets(self, node_ip):
        for bucket in self.node_bkt_map[node_ip]:
            self.delete_bucket(node_ip, bucket)

    def _create_remote_ref(self, src_ip, remote_ip):
        src = self.nodes[src_ip]
        existing_remotes = self.execute_cmd(
            "curl -u " + src["username"] + ':' + src["password"] + " http://" + src_ip + ':' + src["port"] +
            "/pools/default/remoteClusters")
        if remote_ip not in existing_remotes:
            remote = self.nodes[remote_ip]
            self.execute_cmd(
                "curl -v -u " + src["username"] + ':' + src["password"] + " http://" + src_ip + ':' + src["port"] +
                "/pools/default/remoteClusters -d name=" + src_ip + "to" + remote_ip +
                " -d hostname=" + remote_ip + ':' + remote["port"] + " -d username=" + remote[
                    "username"] + " -d password=" + remote["password"])
        return (src_ip + "to" + remote_ip)

    def create_replication(self, src_ip, remote_ip, src_bkt, remote_bkt):
        ref = self._create_remote_ref(src_ip, remote_ip)
        src = self.nodes[src_ip]
        replid = self.execute_cmd(
            "curl -X POST -u " + src["username"] + ':' + src["password"] + " http://" + src_ip + ':' + src["port"] +
            "/controller/createReplication -d fromBucket=" + str(src_bkt) + " -d toCluster=" + ref +
            " -d toBucket=" + str(remote_bkt) + " -d replicationType=continuous")
        replid = str(replid)
        if "id" in replid:
            lines = replid.split('{"id":"')
            for line in range(1, len(lines)):
                repl = lines[line].split('/')[0]
                self.refresh_maps(src_ip, add_repl=repl)

    def delete_replication(self, node_ip, replid):
        node = self.nodes[node_ip]
        self.execute_cmd(
            "curl -X POST -u " + node["username"] + ':' + node["password"] + " http://" + node_ip + ':' + node["port"] +
            "/controller/cancelXDCR/" + replid + " -X DELETE")
        self.refresh_maps(node_ip, drop_repl=replid)

    def change_setting(self, node_ip, replication, setting, val):
        node = self.nodes[node_ip]
        self.execute_cmd(
            "curl -X POST -u " + node["username"] + ':' + node["password"] + " http://" + node_ip + ':' + node["port"] +
            "/settings/replications/" + replication + ' -d ' + setting + '=' + str(val))


if __name__ == '__main__':
    xdcrMgr = XDCRManager()

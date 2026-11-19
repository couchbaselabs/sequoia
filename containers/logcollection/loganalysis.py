import requests
import time
import logging
import dns.resolver
import argparse
import zipfile
import shutil
import subprocess

from datetime import datetime

class LogAnalysis:

    def __init__(self, hostname, username, password, frequency=60, test_name="QE", capella_run=False, iterations=0,
                 collect_only=False):
        self.frequency = frequency
        self.iterations = iterations
        self.collect_only = collect_only
        self.test_name = test_name
        self.hostname = hostname
        self.capella_run = capella_run
        self.log = logging.getLogger("log_collection")
        self.log.setLevel(logging.INFO)
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        ch.setFormatter(formatter)
        self.log.addHandler(ch)
        timestamp = str(datetime.now().strftime('%Y%m%dT_%H%M%S'))
        fh = logging.FileHandler("./loganalysis-{0}.log".format(timestamp))
        fh.setFormatter(formatter)
        self.log.addHandler(fh)
        self.username = username
        self.password = password

    def fetch_rest_url(self, url):
        """
        meant to find the srv record for Capella runs
        """
        srv_info = {}
        srv_records = dns.resolver.resolve('_couchbases._tcp.' + url, 'SRV')
        for srv in srv_records:
            srv_info['host'] = str(srv.target).rstrip('.')
            srv_info['port'] = srv.port
        self.log.info("This is a Capella run. Srv info {}".format(srv_info))
        return srv_info['host']

    def trigger_log_collect(self, upload_url="cb-engineering.s3.amazonaws.com", nodes="*", test_name="QE", timeout=20):
        """
        collects the log bundles for all the nodes in the DP by default. Can be parameterised to
        target specific nodes
        upload_url: S3 bucket to which the logs need to be uploaded
        nodes: * refers to all the nodes
        test_name: Customer field in the upload request
        timeout: duration in minutes
        """
        self.log.info("Trigger log collection")
        if self.capella_run:
            host = self.fetch_rest_url(url=self.hostname)
        else:
            host = self.hostname
        data = f'uploadHost={upload_url}%2F&customer={test_name}&&nodes={nodes}'
        api = f"https://{host}:18091/controller/startLogsCollection"
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        # A cluster runs one log collection at a time and eagle eye starts its own (a cbcollect every scan, about 6 to 8 minutes):
        # a request made while eagle eye's collection is still running is refused with 400. Wait for the running one to
        # finish, and retry a refused request a few times.
        for attempt in range(1, 4):
            self.wait_for_running_collection()
            resp = requests.post(api, data=data, verify=False, headers=headers,
                                 auth=(self.username, self.password))
            if resp.ok:
                break
            # raise_for_status() only says "400 Bad Request": the body says why
            self.log.error(f"startLogsCollection {api} answered {resp.status_code}: {resp.text[:1000]} "
                           f"(request: {data}), attempt {attempt}/3")
            if attempt < 3:
                time.sleep(120)
        if resp.status_code == 400:
            # still refused after waiting and retrying: no bundle this time, but a refused collection must not fail the test
            # (any other HTTP error still raises)
            self.log.warning(f"startLogsCollection was refused with 400 {resp.text[:300]!r} three times: no log bundle "
                             f"for {test_name} this iteration, continuing without error")
            return []
        resp.raise_for_status()
        self.log.info("Log collection triggered. Will wait until the task is complete")
        time.sleep(30)
        log_collection_complete, cb_collect_list, time_now = False, [], time.time()
        while not log_collection_complete and time.time() - time_now < timeout * 60:
            log_collection_task = self.poll_for_tasks("clusterLogsCollection")
            self.log.info(
                f"Waiting for the log collection process to complete. Current task status {log_collection_task}")
            if log_collection_task['status'] == 'completed':
                for perNode in log_collection_task['perNode']:
                    if log_collection_task['perNode'][perNode]['status'] == 'uploaded':
                        cb_collect_list.append(log_collection_task['perNode'][perNode]['url'])
                log_collection_complete = True
            time.sleep(120)
        self.log.info(f"cb_collect bundle for the test {test_name} list: {cb_collect_list}")
        return cb_collect_list

    def collect_logs(self):
        time.sleep(60)
        counter = 1
        while True:
            cbcollect_list = self.trigger_log_collect(test_name=self.test_name)
            self.log.info(f"CbCollect List for iteration {counter}. {cbcollect_list}")
            self.log.info(f"Iteration {counter} log collection complete. Will sleep for {self.frequency*60} seconds")
            time.sleep(self.frequency*60)
            counter += 1

    def wait_for_running_collection(self, timeout=30):
        """Blocks while a cluster log collection is running (someone else's: eagle eye, another test), up to timeout minutes."""
        deadline = time.time() + timeout * 60
        while time.time() < deadline:
            try:
                task = self.poll_for_tasks("clusterLogsCollection")
            except requests.exceptions.RequestException as e:
                self.log.warning(f"could not read the cluster tasks: {e}")
                return
            if not task or task.get('status') != 'running':
                return
            self.log.info(f"A log collection is already running on the cluster (started by someone else): {task.get('status')}, "
                          f"waiting before starting this one")
            time.sleep(30)
        self.log.warning(f"a log collection was still running after {timeout} minutes: trying to start ours anyway")

    def poll_for_tasks(self, task_type):
        api = "https://{}:18091/pools/default/tasks".format(self.hostname)
        resp = requests.get(api, auth=(self.username, self.password), verify=False)
        resp.raise_for_status()
        tasks = resp.json()
        for task in tasks:
            if task['type'] == task_type:
                return task

    def download_logs(self, cb_collect_list):
        for url in cb_collect_list:
            local_filename = url.split('/')[-1]
            with requests.get(url, stream=True) as r:
                with open(local_filename, 'wb') as f:
                    shutil.copyfileobj(r.raw, f)

    def analyze_logs(self,):
        counter = 1
        # iterations=0 keeps the original behaviour: collect (and analyse) forever, every `frequency` minutes
        while not self.iterations or counter <= self.iterations:
            log_list = self.trigger_log_collect(test_name=self.test_name)
            self.log.info(f"CbCollect List for iteration {counter}. {log_list}")
            if self.collect_only:
                log_list = []
            for log in log_list:
                self.log.info(f"Will run the bash analysis script on the log bundle {log}")
                cmd = f"./analyze.sh {log}"
                p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                stdout, stderr = p.communicate()
                if stderr:
                    raise Exception(f"Error from the bash script on {log}")
                if stdout:
                    self.log.info(f"Analysis complete on {log}.\n")
                    self.log.info(f"Keywords hit - \n {stdout} \n")
            if self.iterations and counter >= self.iterations:
                self.log.info(f"Iteration {counter} log collection complete. Done")
                break
            self.log.info(f"Iteration {counter} log collection and analysis complete. Will sleep for {self.frequency * 60} seconds")
            time.sleep(self.frequency * 60)
            counter += 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--hostname", dest="hostname", help="connection string/server IP")
    parser.add_argument("--username", dest="username", default="Administrator", help="user name default=Administrator")
    parser.add_argument("--password", dest="password", default="password", help="password default=password")
    parser.add_argument("--capella_run", dest="capella_run", default="false", help="capella flag, default=false")
    parser.add_argument("--customer_name", dest="customer_name", default="QE",
                        help="customer name that will be used for supportal, default=QE")
    parser.add_argument("--frequency", dest="frequency", default="60", help="how often logs need to get collected")
    parser.add_argument("--iterations", dest="iterations", default="0",
                        help="number of collections to run, then exit. 0 (default) = run forever")
    parser.add_argument("--collect_only", dest="collect_only", default="false",
                        help="true = only collect and upload the logs, skip the keyword analysis, default=false")
    args = parser.parse_args()
    capella_run = True if args.capella_run == 'true' else False
    log_analysis = LogAnalysis(hostname=args.hostname, username=args.username, password=args.password,
                               capella_run=capella_run, test_name=args.customer_name, frequency=int(args.frequency),
                               iterations=int(args.iterations), collect_only=args.collect_only == 'true')
    log_analysis.analyze_logs()
    # sample command to run this image ----
    # docker run sequoiatools/logcollector --hostname <connection string>
    # --username <cluster admin user from Secrets manager> --password <cluster admin password from Secrets manager>
    # --capella_run true --customer_name <Supportal Customer Name> --frequency <log collection frequency>

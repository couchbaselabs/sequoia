import argparse
import logging
import time
import random
import json
import os
from dns import resolver
import requests

from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster
from couchbase.options import (ClusterOptions, ClusterTimeoutOptions,
                               QueryOptions, AnalyticsOptions)
from couchbase.exceptions import CouchbaseException


class QueryManager:
    def __init__(self, connection_string, username, password, timeout, duration, doc_template, use_sdk):
        self.connection_string = connection_string
        self.username = username
        self.password = password
        self.cluster = None
        self.timeout = timeout
        self.duration = duration
        self.template = doc_template
        self.use_sdk = use_sdk == "true"
        self.log = logging.getLogger("query_manager")
        self.log.setLevel(logging.INFO)
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        ch.setFormatter(formatter)
        self.log.addHandler(ch)
        timestamp = str(datetime.now().strftime('%Y%m%dT_%H%M%S'))
        fh = logging.FileHandler("./query_manager-{0}.log".format(timestamp))
        fh.setFormatter(formatter)
        self.log.addHandler(fh)

    def create_cluster_object(self):
        auth = PasswordAuthenticator(self.username, self.password)
        options = ClusterOptions(auth)
        options.apply_profile('wan_development')
        self.cluster = Cluster(f"couchbases://{self.connection_string}?tls_verify=none",
                               options)

    def fetch_rest_url(self):
        srv_info = {}
        srv_records = resolver.resolve('_couchbases._tcp.' + self.connection_string, 'SRV')
        for srv in srv_records:
            srv_info['host'] = str(srv.target).rstrip('.')
            srv_info['port'] = srv.port
        return srv_info['host']

    def fetch_keyspaces_list(self):
        query = """select value ds.DatabaseName || "." || ds.DataverseName || "." || ds.DatasetName 
        from Metadata.`Dataset` as ds where ds.DataverseName <> \"Metadata\""""
        results = self.run_analytics_query(query)
        if self.use_sdk:
            keyspaces = [row for row in results.rows()]
        else:
            keyspaces = results
        return keyspaces

    def run_analytics_query(self, query, iterate_over_results=False):
        if not self.cluster and self.use_sdk:
            self.create_cluster_object()
            self.log.info(f"Will run the query {query}")
            try:
                result = self.cluster.analytics_query(query, AnalyticsOptions(timeout=self.timeout))
                if iterate_over_results:
                    result = [row for row in result.rows()]
                    self.log.info(f"First few rows of the result for the query {query} are {result[:3]}")
                return result
            except:
                import traceback
                self.log.info(f"===========Query {query} has ended in error================================================")
                traceback.print_exc()
        else:
            self.log.info(f"running query - {query} via rest")
            auth = (self.username, self.password)
            payload = {"statement": query}
            api = f"https://" + self.connection_string + ':18095/analytics/service'
            try:
                response = requests.post(url=api, auth=auth, timeout=self.timeout, verify=False,
                                        headers={'Content-Type': 'application/json'},
                                        json=payload)
                if response.status_code == 200:
                    return response.json()['results']
            except:
                pass

    def generate_queries(self):
        self.log.info("Generating queries.")
        generated_queries = []
        with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), "queries.json")) as f:
            data = f.read()
        query_json = json.loads(data)
        if self.template not in query_json:
            raise Exception("Add your query blueprint to queries.json file")
        queries_list = query_json[self.template]
        keyspaces = self.fetch_keyspaces_list()
        for keyspace in keyspaces:
            bucket, scope, collection = keyspace.split(".")
            for item in queries_list:
                query_statement = item.replace("keyspacenameplaceholder", f"`{bucket}`.`{scope}`.`{collection}`")
                generated_queries.append(query_statement)
        self.log.info(f"=====================Generated a total of {len(generated_queries)} queries=====================")
        return generated_queries

    def fetch_active_requests(self):
        query = "select value x from active_requests() as x;"
        results = self.run_analytics_query(query)
        query_results = [row for row in results.rows()]
        active_query_context_id_list = []
        for query in query_results:
            if query['state'] == 'running':
                active_query_context_id_list.append(query['clientContextID'])
        return active_query_context_id_list

    def columnar_admin_rest_call(self, endpoint):
        rest_url = self.fetch_rest_url()
        url = "https://" + rest_url + ":18095/" + endpoint
        self.log.info(f"Will send request to {url} ")
        response = requests.get(url, auth=(
            self.username, self.password), verify=False, timeout=300)
        if response.ok:
            return response.json()

    def fetch_columnar_active_requests(self):
        response = self.columnar_admin_rest_call("analytics/admin/active_requests")
        self.log.info(f"Response is {response} ")
        return response

    def fetch_columnar_completed_requests(self):
        response = self.columnar_admin_rest_call("analytics/admin/completed_requests")
        return response

    def cancel_random_queries(self, cancel_query_count=5):
        active_requests = self.fetch_columnar_active_requests()
        for _ in range(cancel_query_count):
            context_id_to_cancel = random.choice(active_query_context_id_list)
            query = f"cancel {context_id_to_cancel}"
            self.run_analytics_query(query=query)

    # def poll_for_failed_queries(self):
    #     time_now = time.time()
    #     failed_query_metadata, failed_query_count = {}, 0
    #     while time.time() - time_now < self.duration:
    #         response_json = self.fetch_columnar_completed_requests()
    #         for query in response_json:
    #             self.log.debug(f"Parsing {query}")
    #             if query['jobStatus'].lower() not in ['terminated', 'pending', 'running']:
    #                 failed_query_count += 1
    #                 if query['requestTime'] not in failed_query_metadata:
    #                     failed_query_metadata[query['requestTime']] = query
    #         if failed_query_count > 0:
    #             self.log.error(f"Number of failed queries so far {failed_query_count} "
    #                            f"and their metadata {failed_query_metadata}")
    #         self.log.debug(f"Sleeping for 300 seconds before next iteration")
    #         time.sleep(300)
    #     if failed_query_count > 0:
    #         raise Exception("There are failed queries in the completed_requests call. Check logs")
        
    def poll_for_failed_queries(self):
        time_now = time.time()
        failed_query_metadata, failed_query_count = {}, 0
        while time.time() - time_now < self.duration:
            response_json = self.run_analytics_query(query="completed_requests()")
            if response_json:
                for query in response_json[0]:
                    self.log.debug(f"Parsing {query}")
                    if query['jobStatus'].lower() not in ['terminated', 'pending', 'running', 'null']:
                        failed_query_count += 1
                        if query['requestTime'] not in failed_query_metadata:
                            failed_query_metadata[query['requestTime']] = query
                if failed_query_count > 0:
                    self.log.error(f"Number of failed queries so far {failed_query_count} "
                                   f"and their metadata {failed_query_metadata}")
                self.log.debug(f"Sleeping for 300 seconds before next iteration")
                time.sleep(300)
        if failed_query_count > 0:
            raise Exception("There are failed queries in the completed_requests call. Check logs")

    def run_query_workload(self, num_concurrent_queries=5, refresh_duration=1800):
        query_tasks = []
        time_now = time.time()
        time_last_refresh = time.time()
        queries = self.generate_queries()
        while time.time() - time_now < self.duration:
            if time.time() - time_last_refresh >= refresh_duration:
                queries = self.generate_queries()
                time_last_refresh = time.time()
            with ThreadPoolExecutor() as executor_main:
                queries_chosen = random.sample(queries, num_concurrent_queries)
                for query in queries_chosen:
                    query_task = executor_main.submit(self.run_analytics_query, query, True)
                    query_tasks.append(query_task)
            for task in query_tasks:
                task.result()
            sleep_duration = random.randint(10, 60)
            self.log.info(f"Query batch completed. Will sleep for {sleep_duration} seconds")
            time.sleep(sleep_duration)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--connection_string", help="SDK connection string")
    parser.add_argument("-u", "--username", help="username", default="Administrator")
    parser.add_argument("-p", "--password", help="password", default="password")
    parser.add_argument("-t", "--timeout", help="query timeout", default=300)
    parser.add_argument("-b", "--template", help="doc template", default="product")
    parser.add_argument("-d", "--duration", help="duration for which the action needs to run",
                        default=3600)
    parser.add_argument("-q", "--num_concurrent_queries", help="number of queries to be run concurrently",
                        default=5)
    parser.add_argument("-dr", "--refresh_duration", help="duration for which the action needs to run",
                        default=1800)
    parser.add_argument("-a", "--action", help="SDK connection string", default="run_query_workload")
    parser.add_argument("-sd", "--use_sdk", help="use sdk or rest. true for use sdk",
                        default="true")
    args = parser.parse_args()
    query_manager = QueryManager(args.connection_string, args.username, args.password, int(args.timeout),
                                 int(args.duration), args.template, args.use_sdk)
    if args.action == "run_query_workload":
        query_manager.run_query_workload(int(args.num_concurrent_queries), int(args.refresh_duration))
    elif args.action == "poll_for_failed_queries":
        query_manager.poll_for_failed_queries()
    elif args.action == "cancel_random_queries":
        query_manager.cancel_random_queries(int(args.num_concurrent_queries))
    elif args.action == "fetch_active_requests":
        query_manager.fetch_columnar_active_requests()
    else:
        raise Exception("Actions allowed - run_query_workload | poll_for_failed_queries | cancel_random_queries")

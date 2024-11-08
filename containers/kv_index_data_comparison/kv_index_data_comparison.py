import argparse
import logging

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from couchbase.cluster import Cluster
from couchbase.options import ClusterOptions
from couchbase.auth import PasswordAuthenticator
from couchbase.exceptions import DocumentNotFoundException
from couchbase.kv_range_scan import RangeScan, ScanTerm


class KvIndexDataValidation:
    def __init__(self, cluster_ip, result_cluster_ip, bucket, scope, collection, index_fields, batch_size=10000,
                 kv_file='kv_data.jsonl', index_file='index_data.jsonl', result_bucket='kv_index_data_comparison',
                 use_kv_range_scan=False, username='Administrator', password='password',
                 r_username='Administrator', r_password='Password@123'):

        # Create a timestamp for the log filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"/tmp/comparison_log_{timestamp}.log"

        # Configure logging
        self.log = logging.getLogger('kv_index_data_comparison')
        self.log.setLevel(logging.INFO)  # Ensure the logger level is set

        # Prevent duplicate handlers
        if self.log.hasHandlers():
            self.log.handlers.clear()  # Clear any existing handlers

        # Set up formatter
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

        # Add the file handler
        file_handler = logging.FileHandler(log_filename)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        self.log.addHandler(file_handler)

        # Add the console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self.log.addHandler(console_handler)

        # Disable propagation to avoid duplicate logs if using root-level configuration
        self.log.propagate = False

        # Test the logger
        self.log.info(f"Logging initialized. All logs will be stored at {log_filename}")

        self.cluster = Cluster(f'couchbase://{cluster_ip}',
                               ClusterOptions(PasswordAuthenticator(username, password)))
        auth = PasswordAuthenticator(r_username, r_password)
        options = ClusterOptions(auth)
        options.apply_profile("wan_development")
        self.result_cluster = Cluster(f"couchbases://{result_cluster_ip}", options)
        self.bucket = self.cluster.bucket(bucket)
        self.scope = self.bucket.scope(scope)
        self.collection = self.scope.collection(collection)
        self.namespace = f'{bucket}.{scope}.{collection}'
        self.batch_size = int(batch_size)  # Define batch size for fetching index data
        self.kv_file = kv_file
        self.index_file = index_file
        self.index_fields = index_fields
        self.result = None
        self.logfilename = log_filename
        self.result_bucket_name = result_bucket
        self.use_kv_range_scan = use_kv_range_scan

    def fetch_ids_from_index_in_sorted_order(self):
        where_clause = f"{self.index_fields[0]} IS NOT NULL"
        meta_query = (f"SELECT META().id FROM {self.namespace} "
                      f"WHERE {where_clause} "
                      f"ORDER BY META().id")
        self.log.info(f"Running query: {meta_query}")
        result = self.cluster.query(meta_query)
        return [row["id"] for row in result]

    def fetch_data_from_index_in_batches(self):
        offset = 0
        column_str = ", ".join(self.index_fields)
        with open(self.index_file, 'w') as f:
            while True:
                query = (f"SELECT META().id as doc_id, {column_str} FROM {self.namespace} "
                         f"WHERE {self.index_fields[0]} IS NOT NULL "
                         f"ORDER BY META().id LIMIT {self.batch_size} OFFSET {offset}")
                result = self.cluster.query(query)
                self.log.info(f"Running query: {query}")
                batch_fetched = False
                for row in result:
                    f.write(json.dumps(row) + "\n")
                    batch_fetched = True
                f.flush()

                if not batch_fetched:
                    break

                offset += self.batch_size

    def fetch_kv_data_using_range_scan(self, doc_ids):
        with open(self.kv_file, 'w') as f:
            for i in range(0, len(doc_ids), self.batch_size):
                start_doc_id = doc_ids[i]
                end_doc_id = doc_ids[min(i + self.batch_size, len(doc_ids)) - 1]
                self.log.info(f"KV data fetch: {start_doc_id} - {end_doc_id}")
                start_term = ScanTerm(term=start_doc_id, exclusive=False)
                end_term = ScanTerm(term=end_doc_id, exclusive=False)

                scan = RangeScan(start=start_term, end=end_term)

                batch = []  # Store the KV data in a batch
                start_time = time.time()
                for scan_result in self.collection.scan(scan):
                    doc_id = scan_result.key
                    try:
                        doc = scan_result.content_as[dict]
                        kv_data = {field: doc.get(field) for field in self.index_fields}
                        kv_data["doc_id"] = doc_id
                        batch.append(kv_data)
                    except DocumentNotFoundException:
                        self.log.info(f"Document {doc_id} not found in KV service.")
                end_time = time.time()
                time_elapsed = end_time - start_time
                self.log.info(f"Time taken to fetch {self.batch_size} docs from KV - {time_elapsed:.6f} secs")
                # Write the entire batch to the file in one operation
                if batch:
                    f.writelines(json.dumps(entry) + "\n" for entry in batch)
                    f.flush()

    def fetch_kv_data_using_get(self, doc_ids):
        # Define a helper function to fetch a single document
        def fetch_document(doc_id):
            try:
                doc = self.collection.get(doc_id)
                kv_data = {field: doc.content_as[dict].get(field) for field in index_fields}
                kv_data["doc_id"] = doc_id
                return kv_data
            except DocumentNotFoundException:
                self.log.info(f"Document {doc_id} not found in KV service.")
                return None

        # Fetch documents in parallel
        with open(self.kv_file, 'w') as f:
            with ThreadPoolExecutor() as executor:
                # Process in batches
                for i in range(0, len(doc_ids), self.batch_size):
                    kv_data_list = []
                    batch = doc_ids[i:i + batch_size]
                    self.log.info(f"Fetching KV data for docs: {batch[0]} - {batch[-1]}")
                    start_time = time.time()
                    # Submit tasks for the current batch
                    results = list(executor.map(fetch_document, batch))
                    # Filter out any None results for documents not found
                    kv_data_list.extend(filter(None, results))
                    end_time = time.time()
                    time_elapsed = end_time - start_time
                    self.log.info(f"Time taken to fetch {self.batch_size} docs: {time_elapsed:.6f} secs")

                    # Write all fetched data to file
                    for kv_data in kv_data_list:
                        f.write(json.dumps(kv_data) + "\n")
                        f.flush()

    def load_data_batch(self, file, batch_size):
        batch = []
        for line in file:
            batch.append(json.loads(line))
            if len(batch) == batch_size:
                yield batch
                batch = []
        if batch:
            yield batch

    def write_result_couchbase_bucket(self):
        result_bucket = self.result_cluster.bucket(self.result_bucket_name)
        result_collection = result_bucket.default_collection()

        # Insert the document into the result bucket
        doc_id = self.logfilename.split('/')[1].split('.')[0]
        val = self.result
        try:
            result_collection.upsert(doc_id, val)
            self.log.info(
                f"Result successfully written to Couchbase bucket '{self.result_bucket_name}' with doc ID '{doc_id}'.")
        except Exception as e:
            self.log.error(f"Failed to write result to Couchbase bucket '{self.result_bucket_name}': {e}")

    def compare_kv_index_files_in_batches(self):
        failed_docs = []
        status = "PASS"
        with open(self.kv_file, 'r') as kv_f, open(self.index_file, 'r') as idx_f:
            kv_batch_generator = self.load_data_batch(kv_f, self.batch_size)
            idx_batch_generator = self.load_data_batch(idx_f, self.batch_size)

            all_kv_doc_ids = set()
            all_idx_doc_ids = set()

            for kv_batch in kv_batch_generator:
                kv_data_dict = {item["doc_id"]: item for item in kv_batch}
                all_kv_doc_ids.update(kv_data_dict.keys())

                if idx_batch_generator:
                    try:
                        idx_batch = next(idx_batch_generator)
                    except StopIteration:
                        idx_batch = []

                    idx_data_dict = {item["doc_id"]: item for item in idx_batch}
                    all_idx_doc_ids.update(idx_data_dict.keys())

                    for doc_id, index_data in idx_data_dict.items():
                        kv_data = kv_data_dict.get(doc_id)
                        if kv_data is None:
                            self.log.warning(f"Document {doc_id} is missing in KV data.")
                            failed_docs.append(doc_id)
                        elif kv_data != index_data:
                            self.log.warning(
                                f"Data mismatch for document {doc_id}. Index data: {index_data}, KV data: {kv_data}")
                            failed_docs.append(doc_id)

            for doc_id in all_kv_doc_ids - all_idx_doc_ids:
                self.log.warning(f"Extra document {doc_id} found in KV data but missing in Index data.")
                failed_docs.append(doc_id)

            for doc_id in all_idx_doc_ids - all_kv_doc_ids:
                self.log.warning(f"Extra document {doc_id} found in Index data but missing in KV data.")
                failed_docs.append(doc_id)

        if failed_docs:
            status = "FAIL"

        # Print the status and failed document IDs as JSON to be captured by the calling script
        result = {
            "status": status,
            "failed_docs": failed_docs
        }
        self.log.info(json.dumps(result))
        self.result = result

    def compare_data_between_kv_and_index(self):

        # Step 1: Fetch sorted document IDs from index
        sorted_doc_ids = self.fetch_ids_from_index_in_sorted_order()

        # Step 2: Fetch index data in batches and write to file
        self.fetch_data_from_index_in_batches()

        # Step 3: Fetch KV data using sorted doc IDs in batches and write to file
        if self.use_kv_range_scan:
            self.fetch_kv_data_using_range_scan(sorted_doc_ids)
        else:
            self.fetch_kv_data_using_get(sorted_doc_ids)

        # Step 4: Compare KV and Index data in batches
        self.compare_kv_index_files_in_batches()

        # Step 5: Write result to bucket to retrieve it later and return the result to caller
        self.write_result_couchbase_bucket()

        output_file = "/tmp/comparison_result.json"

        # Write result to the output file
        with open(output_file, 'w') as f:
            json.dump(val_obj.result, f)

        self.log.info(f"Saved the result in {output_file}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--index_fields",
                        help="Provide the document fields on which index is created. Order of the field is important")
    parser.add_argument("-i", "--cluster_ip", help="Used to directly interact with the node")
    parser.add_argument("-r", "--result_cluster_ip", help="Node address to store the result")
    parser.add_argument('-u', '--username', help="Username of Cluster with data", default="Administrator")
    parser.add_argument('-p', '--password', help="Password of Cluster with data", default="password")
    parser.add_argument('-m', '--r_username', help="Username of Result Cluster", default="Administrator")
    parser.add_argument('-n', '--r_password', help="Password of Result Cluster", default="Password@123")
    parser.add_argument("-b", "--bucket", help="Used to directly interact with the node")
    parser.add_argument("-x", "--result_bucket", help="Used to directly interact with the node")
    parser.add_argument("-s", "--scope", help="Used to directly interact with the node")
    parser.add_argument("-k", "--use_kv_range_scan",
                        help="Used get to fetch KV data one document at a time", action='store_true')
    parser.add_argument("-c", "--collection", help="Used to directly interact with the node")
    parser.add_argument("-z", "--batch_size", help="Size of the batch to fetch the data for Index and KV",
                        default="10000")
    args = parser.parse_args()
    index_fields = args.index_fields.split(',')
    cluster_ip = args.cluster_ip
    result_cluster_ip = args.result_cluster_ip
    bucket = args.bucket
    result_bucket = args.result_bucket
    scope = args.scope
    collection = args.collection
    use_kv_range_scan = args.use_kv_range_scan
    username = args.username
    password = args.password
    r_username = args.r_username
    r_password = args.r_password

    batch_size = int(args.batch_size)
    val_obj = KvIndexDataValidation(cluster_ip=cluster_ip, result_cluster_ip=result_cluster_ip,
                                    bucket=bucket, result_bucket=result_bucket,
                                    scope=scope, index_fields=index_fields, collection=collection,
                                    batch_size=batch_size, use_kv_range_scan=use_kv_range_scan, username=username,
                                    r_username=r_username, password=password, r_password=r_password)
    val_obj.compare_data_between_kv_and_index()
    sys.exit(0 if not val_obj.result['failed_docs'] else 1)

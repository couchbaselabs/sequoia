"""
RRF (Reciprocal Rank Fusion) Dataset Loader.

Supports MS MARCO passage ranking and BEIR (SciFact, NFCorpus) datasets.
Downloads datasets, generates embeddings using sentence-transformers, and loads
documents into Couchbase with both text and vector fields for RRF validation.
"""

import csv
import json
import os
import tarfile
import threading
import time
import zipfile
import random
import argparse
import concurrent.futures
from datetime import timedelta
from pathlib import Path
from urllib.request import urlretrieve

import numpy as np
import requests
import dns.resolver
import paramiko

from couchbase.cluster import Cluster, ClusterOptions, ClusterTimeoutOptions
from couchbase.auth import PasswordAuthenticator
from couchbase.exceptions import (
    BucketAlreadyExistsException,
    CollectionAlreadyExistsException,
    ScopeAlreadyExistsException
)
from couchbase.management.buckets import BucketType, CreateBucketSettings, ConflictResolutionType
from couchbase.management.collections import CollectionSpec

MSMARCO_URLS = {
    "collection": "https://msmarco.z22.web.core.windows.net/msmarcoranking/collection.tar.gz",
    "queries": "https://msmarco.z22.web.core.windows.net/msmarcoranking/queries.tar.gz",
    "qrels_dev_small": "https://msmarco.z22.web.core.windows.net/msmarcoranking/qrels.dev.small.tsv",
}

BEIR_BASE_URL = "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets"

BEIR_DATASETS = {
    "scifact": {
        "url": f"{BEIR_BASE_URL}/scifact.zip",
        "corpus_size": 5183,
        "query_count": 300,
        "description": "Fact verification against scientific literature"
    },
    "nfcorpus": {
        "url": f"{BEIR_BASE_URL}/nfcorpus.zip",
        "corpus_size": 3633,
        "query_count": 323,
        "description": "Biomedical information retrieval"
    }
}

SUPPORTED_DATASETS = ["msmarco", "scifact", "nfcorpus"]

LOCAL_BASE_DIR = "/tmp/rrf_datasets"
MSMARCO_DIR = os.path.join(LOCAL_BASE_DIR, "msmarco")
BEIR_DIR = os.path.join(LOCAL_BASE_DIR, "beir")
EMBEDDING_CACHE_DIR = os.path.join(LOCAL_BASE_DIR, "embeddings_cache")

DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"
DEFAULT_EMBEDDING_DIM = 384
MAX_THREADS = 10
EMBEDDING_BATCH_SIZE = 64


class MSMarcoDataset:
    """Downloads and manages MS MARCO passage ranking dataset."""

    def __init__(self, max_passages=0, qrel_only=False):
        self.max_passages = max_passages
        self.qrel_only = qrel_only
        self.passages = {}
        self.queries = {}
        self.qrels = {}

    def download_and_extract(self):
        os.makedirs(MSMARCO_DIR, exist_ok=True)

        qrels_path = os.path.join(MSMARCO_DIR, "qrels.dev.small.tsv")
        if not os.path.exists(qrels_path):
            print(f"Downloading qrels to {qrels_path}")
            urlretrieve(MSMARCO_URLS["qrels_dev_small"], qrels_path)
        self._parse_qrels(qrels_path)

        queries_tar_path = os.path.join(MSMARCO_DIR, "queries.tar.gz")
        queries_tsv_path = os.path.join(MSMARCO_DIR, "queries.dev.tsv")
        if not os.path.exists(queries_tsv_path):
            if not os.path.exists(queries_tar_path):
                print(f"Downloading queries to {queries_tar_path}")
                urlretrieve(MSMARCO_URLS["queries"], queries_tar_path)
            with tarfile.open(queries_tar_path, "r:gz") as tar:
                tar.extractall(MSMARCO_DIR)
        self._parse_queries(queries_tsv_path)

        collection_tar_path = os.path.join(MSMARCO_DIR, "collection.tar.gz")
        collection_tsv_path = os.path.join(MSMARCO_DIR, "collection.tsv")
        if not os.path.exists(collection_tsv_path):
            if not os.path.exists(collection_tar_path):
                print(f"Downloading collection to {collection_tar_path}")
                urlretrieve(MSMARCO_URLS["collection"], collection_tar_path)
            with tarfile.open(collection_tar_path, "r:gz") as tar:
                tar.extractall(MSMARCO_DIR)
        self._parse_collection(collection_tsv_path)

        print(f"Loaded {len(self.passages)} passages, {len(self.queries)} queries, "
              f"{len(self.qrels)} query-relevance judgments")

    def _parse_qrels(self, path):
        with open(path, "r") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) == 4:
                    qid, _, pid, relevance = parts
                    qid, pid, relevance = int(qid), int(pid), int(relevance)
                    if qid not in self.qrels:
                        self.qrels[qid] = {}
                    self.qrels[qid][pid] = relevance

    def _parse_queries(self, path):
        with open(path, "r") as f:
            reader = csv.reader(f, delimiter="\t")
            for row in reader:
                if len(row) == 2:
                    qid, text = int(row[0]), row[1]
                    if qid in self.qrels:
                        self.queries[qid] = text

    def _parse_collection(self, path):
        relevant_pids = set()
        if self.qrel_only:
            for qid_rels in self.qrels.values():
                relevant_pids.update(qid_rels.keys())
            print(f"Filtering to {len(relevant_pids)} relevant passage IDs from qrels")

        count = 0
        with open(path, "r") as f:
            reader = csv.reader(f, delimiter="\t")
            for row in reader:
                if len(row) >= 2:
                    pid, text = int(row[0]), row[1]
                    if self.qrel_only and pid not in relevant_pids:
                        continue
                    self.passages[pid] = text
                    count += 1
                    if self.max_passages > 0 and count >= self.max_passages:
                        break
                    if count % 100000 == 0:
                        print(f"Parsed {count} passages...")

    def get_passage_list(self):
        return [(pid, text) for pid, text in self.passages.items()]

    def get_query_list(self):
        return [(qid, text) for qid, text in self.queries.items()]


class BEIRDataset:
    """Downloads and manages BEIR datasets (SciFact, NFCorpus)."""

    def __init__(self, dataset_name, max_passages=0):
        if dataset_name not in BEIR_DATASETS:
            raise ValueError(f"Unsupported BEIR dataset: {dataset_name}. "
                             f"Supported: {list(BEIR_DATASETS.keys())}")
        self.dataset_name = dataset_name
        self.max_passages = max_passages
        self.dataset_config = BEIR_DATASETS[dataset_name]
        self.dataset_dir = os.path.join(BEIR_DIR, dataset_name)
        self.passages = {}
        self.queries = {}
        self.qrels = {}

    def download_and_extract(self):
        os.makedirs(BEIR_DIR, exist_ok=True)

        zip_path = os.path.join(BEIR_DIR, f"{self.dataset_name}.zip")
        if not os.path.exists(self.dataset_dir):
            if not os.path.exists(zip_path):
                print(f"Downloading BEIR/{self.dataset_name} to {zip_path}")
                urlretrieve(self.dataset_config["url"], zip_path)
            print(f"Extracting {zip_path} to {BEIR_DIR}")
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(BEIR_DIR)

        self._parse_corpus()
        self._parse_queries()
        self._parse_qrels()

        print(f"[{self.dataset_name}] Loaded {len(self.passages)} passages, "
              f"{len(self.queries)} queries, {len(self.qrels)} query-relevance judgments")

    def _parse_corpus(self):
        corpus_path = os.path.join(self.dataset_dir, "corpus.jsonl")
        if not os.path.exists(corpus_path):
            raise FileNotFoundError(f"Corpus file not found: {corpus_path}")

        count = 0
        with open(corpus_path, "r") as f:
            for line in f:
                doc = json.loads(line.strip())
                doc_id = doc["_id"]
                title = doc.get("title", "")
                text = doc.get("text", "")
                passage_text = (title + " " + text).strip() if title else text
                self.passages[doc_id] = passage_text
                count += 1
                if self.max_passages > 0 and count >= self.max_passages:
                    break

    def _parse_queries(self):
        queries_path = os.path.join(self.dataset_dir, "queries.jsonl")
        if not os.path.exists(queries_path):
            raise FileNotFoundError(f"Queries file not found: {queries_path}")

        with open(queries_path, "r") as f:
            for line in f:
                doc = json.loads(line.strip())
                qid = doc["_id"]
                text = doc.get("text", "")
                self.queries[qid] = text

    def _parse_qrels(self):
        qrels_dir = os.path.join(self.dataset_dir, "qrels")
        qrels_path = os.path.join(qrels_dir, "test.tsv")
        if not os.path.exists(qrels_path):
            qrels_path = os.path.join(qrels_dir, "dev.tsv")
        if not os.path.exists(qrels_path):
            print(f"Warning: No qrels file found in {qrels_dir}")
            return

        with open(qrels_path, "r") as f:
            reader = csv.reader(f, delimiter="\t")
            header = next(reader, None)
            for row in reader:
                if len(row) >= 3:
                    qid = row[0]
                    doc_id = row[1]
                    relevance = int(row[2])
                    if qid not in self.qrels:
                        self.qrels[qid] = {}
                    self.qrels[qid][doc_id] = relevance

        self.queries = {qid: text for qid, text in self.queries.items()
                        if qid in self.qrels}

    def get_passage_list(self):
        return [(pid, text) for pid, text in self.passages.items()]

    def get_query_list(self):
        return [(qid, text) for qid, text in self.queries.items()]


class EmbeddingGenerator:
    """Generates embeddings using sentence-transformers."""

    def __init__(self, model_name=DEFAULT_MODEL_NAME):
        self.model_name = model_name
        self.model = None
        self.dimension = DEFAULT_EMBEDDING_DIM

    def _load_model(self):
        if self.model is None:
            from sentence_transformers import SentenceTransformer
            print(f"Loading embedding model: {self.model_name}")
            self.model = SentenceTransformer(self.model_name)
            self.dimension = self.model.get_sentence_embedding_dimension()
            print(f"Model loaded. Embedding dimension: {self.dimension}")

    def encode_batch(self, texts, batch_size=EMBEDDING_BATCH_SIZE):
        self._load_model()
        embeddings = self.model.encode(
            texts, batch_size=batch_size,
            show_progress_bar=True, normalize_embeddings=True
        )
        return embeddings

    def encode_and_cache(self, passages, cache_key="msmarco"):
        os.makedirs(EMBEDDING_CACHE_DIR, exist_ok=True)
        cache_file = os.path.join(EMBEDDING_CACHE_DIR, f"{cache_key}_{len(passages)}.npz")

        if os.path.exists(cache_file):
            print(f"Loading cached embeddings from {cache_file}")
            data = np.load(cache_file, allow_pickle=True)
            return list(data["pids"]), data["embeddings"]

        pids = [p[0] for p in passages]
        texts = [p[1] for p in passages]

        print(f"Generating embeddings for {len(texts)} passages...")
        embeddings = self.encode_batch(texts)

        np.savez(cache_file, pids=np.array(pids, dtype=object), embeddings=embeddings)
        print(f"Cached embeddings to {cache_file}")

        return pids, embeddings


class DocKey:
    def __init__(self, prefix="", start=0):
        self.start_key = start
        self.counter = start
        self.prefix = prefix
        self.key_lock = threading.Lock()

    def get_next_key(self):
        with self.key_lock:
            self.counter += 1
            doc_key = self.prefix + str(self.counter)
            return doc_key, self.counter

    def get_key(self, doc_index):
        doc_key = self.prefix + str(doc_index + 1 + self.start_key)
        return doc_key


class RRFLoader:

    def __init__(self):
        parser = argparse.ArgumentParser(description="RRF Dataset Loader for MS MARCO and BEIR")
        parser.add_argument("-n", "--node", help="Couchbase Server Node Address", required=True)
        parser.add_argument("-u", "--username", help="Couchbase Server Cluster Username", required=True)
        parser.add_argument("-p", "--password", help="Couchbase Server Cluster Password", required=True)
        parser.add_argument("-b", "--bucket", help="Bucket name", default="")
        parser.add_argument("-sc", "--scope", help="Scope name", default="")
        parser.add_argument("-coll", "--collection", help="Collection name for passages", default="")
        parser.add_argument("-ds", "--dataset",
                            choices=SUPPORTED_DATASETS,
                            default="msmarco",
                            help=f"Dataset to load. Choices: {', '.join(SUPPORTED_DATASETS)}")
        parser.add_argument("-c", "--capella", default=False,
                            help="Set to True for Capella runs")
        parser.add_argument("-cbs", "--create_bucket_structure", default=True,
                            help="Create bucket, scope, collection if they don't exist")
        parser.add_argument("-max", "--max_passages", type=int, default=0,
                            help="Max passages to load. 0 = all relevant passages from qrels")
        parser.add_argument("--qrel_only", default="True",
                            help="Only load passages referenced in qrels (default: True, MS MARCO only)")
        parser.add_argument("-model", "--model_name", default=DEFAULT_MODEL_NAME,
                            help="Sentence-transformer model name for embeddings")
        parser.add_argument("-a", "--action",
                            choices=["load_passages", "load_queries", "load_all"],
                            default="load_all",
                            help="Action to perform")
        parser.add_argument("-sk", "--start_key", type=int, default=0,
                            help="Start index for doc IDs")
        parser.add_argument("-slave_ip", "--slave_ip",
                            help="Slave node for remote operations", default="")

        args = parser.parse_args()
        self.node = args.node
        self.username = args.username
        self.password = args.password
        self.dataset_name = args.dataset
        self.bucket = args.bucket or f"rrf_{self.dataset_name}"
        self.scope = args.scope or "rrf_scope"
        self.collection = args.collection or "passages"
        self.capella_run = str(args.capella).lower() == "true"
        self.cbs = str(args.create_bucket_structure).lower() == "true"
        self.max_passages = args.max_passages
        self.qrel_only = str(args.qrel_only).lower() == "true"
        self.model_name = args.model_name
        self.action = args.action
        self.start_key = args.start_key
        self.slave_ip = args.slave_ip

        print(f"Config: node={self.node}, dataset={self.dataset_name}, bucket={self.bucket}, "
              f"scope={self.scope}, collection={self.collection}, capella={self.capella_run}, "
              f"cbs={self.cbs}, max_passages={self.max_passages}, qrel_only={self.qrel_only}, "
              f"model={self.model_name}, action={self.action}")

    def fetch_rest_url(self, url):
        if "cb." not in url:
            return url
        print(f"This is a Capella run. Finding the srv domain for {url}")
        srv_info = {}
        srv_records = dns.resolver.query('_couchbases._tcp.' + url, 'SRV')
        for srv in srv_records:
            srv_info['host'] = str(srv.target).rstrip('.')
            srv_info['port'] = srv.port
        print(f"Srv info {srv_info}")
        return srv_info['host']

    def _get_cluster(self):
        auth = PasswordAuthenticator(self.username, self.password)
        if self.capella_run:
            timeout_options = ClusterTimeoutOptions(
                kv_timeout=timedelta(seconds=120),
                query_timeout=timedelta(seconds=10)
            )
            options = ClusterOptions(auth, timeout_options=timeout_options)
            cluster = Cluster(
                f"couchbases://{self.node}?ssl=no_verify", options
            )
        else:
            cluster = Cluster(f"couchbase://{self.node}", ClusterOptions(auth))
        return cluster

    def _create_bucket_scope_collection(self, cluster, collection_name=None):
        if collection_name is None:
            collection_name = self.collection

        bucket_manager = cluster.buckets()
        try:
            bucket_manager.create_bucket(
                CreateBucketSettings(
                    name=self.bucket,
                    flush_enabled=True,
                    ram_quota_mb=256,
                    num_replicas=0,
                    conflict_resolution_type=ConflictResolutionType.SEQUENCE_NUMBER,
                    bucket_type=BucketType.COUCHBASE
                )
            )
            print(f"Created bucket: {self.bucket}")
        except BucketAlreadyExistsException:
            print(f"Bucket {self.bucket} already exists")

        time.sleep(5)
        bucket = cluster.bucket(self.bucket)
        coll_manager = bucket.collections()

        try:
            coll_manager.create_scope(self.scope)
            print(f"Created scope: {self.scope}")
            time.sleep(5)
        except ScopeAlreadyExistsException:
            print(f"Scope {self.scope} already exists")
        except Exception as e:
            print(f"Scope creation note: {e}")

        try:
            coll_manager.create_collection(
                CollectionSpec(collection_name, scope_name=self.scope)
            )
            print(f"Created collection: {collection_name}")
            time.sleep(5)
        except CollectionAlreadyExistsException:
            print(f"Collection {collection_name} already exists")
        except Exception as e:
            print(f"Collection creation note: {e}")

        time.sleep(10)
        return bucket.scope(self.scope).collection(collection_name)

    def _upsert_document(self, collection, doc_id, document):
        for retry in range(3):
            try:
                collection.upsert(doc_id, document)
                return True
            except Exception as e:
                print(f"Error upserting {doc_id}: {e}, retry {retry + 1}")
                time.sleep(1)
        return False

    def _parallel_upsert(self, collection, doc_pairs, label="docs"):
        """Upsert a list of (doc_id, document) pairs using a thread pool."""
        total = len(doc_pairs)
        completed = [0]
        failed = [0]
        lock = threading.Lock()

        def _do_upsert(pair):
            doc_id, document = pair
            success = self._upsert_document(collection, doc_id, document)
            with lock:
                if success:
                    completed[0] += 1
                else:
                    failed[0] += 1
                done = completed[0] + failed[0]
                if done % 500 == 0 or done == total:
                    print(f"[{self.dataset_name}] {label}: {done}/{total} "
                          f"(failed: {failed[0]})")

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
            executor.map(_do_upsert, doc_pairs)

        print(f"[{self.dataset_name}] {label} complete: {completed[0]} succeeded, "
              f"{failed[0]} failed out of {total}")

    def _create_dataset(self):
        if self.dataset_name == "msmarco":
            dataset = MSMarcoDataset(
                max_passages=self.max_passages,
                qrel_only=self.qrel_only
            )
        else:
            dataset = BEIRDataset(
                dataset_name=self.dataset_name,
                max_passages=self.max_passages
            )
        dataset.download_and_extract()
        return dataset

    def load_data(self):
        dataset = self._create_dataset()

        embedding_gen = EmbeddingGenerator(self.model_name)

        cluster = self._get_cluster()

        if self.action in ("load_passages", "load_all"):
            if self.cbs and not self.capella_run:
                passages_coll = self._create_bucket_scope_collection(cluster, self.collection)
            else:
                bucket = cluster.bucket(self.bucket)
                passages_coll = bucket.scope(self.scope).collection(self.collection)
            self._load_passages(dataset, embedding_gen, passages_coll)

        if self.action in ("load_queries", "load_all"):
            if self.cbs and not self.capella_run:
                queries_coll = self._create_bucket_scope_collection(cluster, "queries")
            else:
                bucket = cluster.bucket(self.bucket)
                queries_coll = bucket.scope(self.scope).collection("queries")
            self._load_queries(dataset, embedding_gen, queries_coll)

    def _load_passages(self, dataset, embedding_gen, collection):
        passages = dataset.get_passage_list()
        if not passages:
            print("No passages to load")
            return

        cache_key = self.dataset_name
        print(f"[{self.dataset_name}] Generating embeddings for {len(passages)} passages...")
        pids, embeddings = embedding_gen.encode_and_cache(passages, cache_key=cache_key)

        pid_to_text = {p[0]: p[1] for p in passages}
        doc_prefix = self.dataset_name

        print(f"[{self.dataset_name}] Building {len(passages)} passage documents...")
        doc_pairs = []
        for pid, embedding in zip(pids, embeddings):
            pid_key = pid.item() if hasattr(pid, 'item') else pid
            doc_id = f"{doc_prefix}_{pid_key}"
            passage_text = pid_to_text.get(pid_key, "")
            if not passage_text:
                passage_text = pid_to_text.get(str(pid_key), "")
            document = {
                "passage_id": pid_key,
                "passage_text": passage_text,
                "vector_data": embedding.tolist(),
                "dim": int(embedding_gen.dimension),
                "dataset": self.dataset_name,
                "type": "passage"
            }
            doc_pairs.append((doc_id, document))

        self._parallel_upsert(collection, doc_pairs, label="passages")

    def _load_queries(self, dataset, embedding_gen, collection):
        queries = dataset.get_query_list()
        if not queries:
            print("No queries to load")
            return

        query_texts = [q[1] for q in queries]
        print(f"[{self.dataset_name}] Generating embeddings for {len(queries)} queries...")
        query_embeddings = embedding_gen.encode_batch(query_texts)

        doc_prefix = self.dataset_name
        doc_pairs = []
        for (qid, text), embedding in zip(queries, query_embeddings):
            doc_id = f"{doc_prefix}_query_{qid}"
            relevant_passages = {}
            for pid, rel in dataset.qrels.get(qid, {}).items():
                relevant_passages[str(pid)] = rel
            document = {
                "query_id": qid,
                "query_text": text,
                "query_vector": embedding.tolist(),
                "relevant_passages": relevant_passages,
                "dataset": self.dataset_name,
                "type": "query"
            }
            doc_pairs.append((doc_id, document))

        self._parallel_upsert(collection, doc_pairs, label="queries")


if __name__ == "__main__":
    loader = RRFLoader()
    loader.load_data()

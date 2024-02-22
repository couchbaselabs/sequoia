"""
Downloads dataset, extract vectors and dumps into couchbase.
"""

import glob
import os
import re
import shutil
import socket
import struct
import tarfile
from urllib.request import urlretrieve
from pathlib import Path
from couchbase.cluster import Cluster, ClusterOptions
from couchbase.auth import PasswordAuthenticator
import h5py
import numpy as np
import wget
import concurrent.futures
import uuid
import json
import paramiko
import threading
from functools import partial
from couchbase.exceptions import (
    BucketAlreadyExistsException,
    CollectionAlreadyExistsException,
    ScopeAlreadyExistsException
)
from couchbase.management.buckets import BucketType, CreateBucketSettings, ConflictResolutionType
from couchbase.management.collections import CollectionSpec

import requests
import argparse
import time
import random
import dns.resolver
from couchbase.cluster import ClusterTimeoutOptions
from datetime import timedelta
import faiss

########################################################################################
# Global Variables
########################################################################################
MAX_THREADS = 1
# Map of all available HDF5 formatted dataset.
HDF5_FORMATTED_DATASETS = {
    "fashion-mnist": {
        "dataset_name": "fashion-mnist",
        "dimension": 784,
        "train_size": 60000,
        "test_size": 10000,
        "neighbors": 100,
        "distance_type": "euclidean",
        "url": "http://ann-benchmarks.com/fashion-mnist-784-euclidean.hdf5",
        "local_file_path": "/tmp/vectordb_datasets/hdf5_format_datasets/fashion-mnist-784-euclidean.hdf5",
    },
    "gist": {
        "dataset_name": "gist",
        "dimension": 960,
        "train_size": 1000000,
        "test_size": 1000,
        "neighbors": 100,
        "distance_type": "euclidean",
        "url": "http://ann-benchmarks.com/gist-960-euclidean.hdf5",
        "local_file_path": "/tmp/vectordb_datasets/hdf5_format_datasets/gist-960-euclidean.hdf5",
    },
    "mnist": {
        "dataset_name": "mnist",
        "dimension": 784,
        "train_size": 60000,
        "test_size": 10000,
        "neighbors": 100,
        "distance_type": "euclidean",
        "url": "http://ann-benchmarks.com/mnist-784-euclidean.hdf5",
        "local_file_path": "/tmp/vectordb_datasets/hdf5_format_datasets/mnist-784-euclidean.hdf5",
    },
    "sift": {
        "dataset_name": "sift",
        "dimension": 128,
        "train_size": 1000000,
        "test_size": 10000,
        "neighbors": 100,
        "distance_type": "euclidean",
        "url": "http://ann-benchmarks.com/sift-128-euclidean.hdf5",
        "local_file_path": "/tmp/vectordb_datasets/hdf5_format_datasets/sift-128-euclidean.hdf5"
    },
}


########################################################################################

class VectorDataset:
    """
    Deals with SIFT/GIST data set at http://corpus-texmex.irisa.fr/
    """

    dataset_name = ""
    dataset_path = ""
    sift_base_url = ""
    train_dataset_filepath = ""
    query_dataset_filepath = ""
    learn_dataset_filepath = ""
    groundtruth_dataset_filepath = ""

    supported_sift_datasets = ["sift", "siftsmall", "gist"]
    local_base_dir = "/tmp/vectordb_datasets"

    sift_dataset_dims = {
        "sift": 128,
        "siftsmall": 128
    }

    train_vecs = None
    query_vecs = None
    learn_vecs = None
    neighbors_vecs = None
    distances_vecs = None
    num_train_vecs = 0
    num_query_vecs = 0
    num_learn_vecs = 0
    num_neighbors_vecs = 0
    num_distances_vecs = 0

    def __init__(self, dataset_name):
        self.dataset_name = dataset_name
        self.sift_base_url = "ftp://ftp.irisa.fr/local/texmex/corpus/"
        print(f"Initialized dataset name:{self.dataset_name}, dataset base_url:{self.sift_base_url}")

    def print_details(self):
        """
        Only for debugging purpose to check all the paths and variable set.
        """
        print(f"Dataset Name: {self.dataset_name}")
        print(f"Dataset Path: {self.dataset_path}")
        print(f"Sift_base_url: {self.sift_base_url}")
        print(f"Train dataset filepath: {self.train_dataset_filepath}")
        print(f"Query dataset filepath: {self.query_dataset_filepath}")
        print(f"Learn dataset filepath: {self.learn_dataset_filepath}")
        print(f"Ground Truth dataset filepath: {self.groundtruth_dataset_filepath}")
        print(f"Supported sift datasets: {self.supported_sift_datasets}")

    def download_dataset(self):
        """
        Supported dataset names: siftsmall and sift. Once dataset is downloaded
        it sets self.dataset_path path

        Args:

        Returns: The local_base_dir where the dataset was downloaded.
        """
        print(f"Downloading dataset {self.dataset_name}")
        if self.dataset_name not in self.supported_sift_datasets:
            print(
                f"Error: {self.dataset_name} not supported, "
                f"only {', '.join(self.supported_sift_datasets)} supported"
            )
        else:
            tar_file_name = self.dataset_name + ".tar.gz"  # Ex: sift.tar.gz
            local_tar_file_path = os.path.join(self.local_base_dir,
                                               tar_file_name)  # Ex: /tmp/vectordb_datasets/sift.tar.gz
            sift_tar_file_url = os.path.join(self.sift_base_url, tar_file_name)
            if not os.path.exists(self.local_base_dir):
                Path(self.local_base_dir).mkdir(parents=True, exist_ok=True)
            dataset_dir_path = os.path.join(self.local_base_dir, self.dataset_name)  # Ex: /tmp/vectordb_datasets/sift
            if os.path.exists(dataset_dir_path):  # Remove existing dir Ex: /tmp/vectordb_datasets/sift
                shutil.rmtree(dataset_dir_path)

            if not os.path.exists(local_tar_file_path):
                try:
                    # Changing permissions to allow wget to write files
                    self.change_permissions(self.local_base_dir)
                    print(f"Downloading {sift_tar_file_url} to {self.local_base_dir}")
                    wget.download(sift_tar_file_url, out=self.local_base_dir)
                    # Changing permissions to all files after downloading.
                    self.change_permissions(self.local_base_dir)
                except Exception as e:
                    print(
                        f"Unable to get file from  {sift_tar_file_url} to local dir {self.local_base_dir}"
                        f"exception {e}"
                    )
            else:
                print(f"Skipping download as tar file as it exists at the path {local_tar_file_path} already")
            with tarfile.open(local_tar_file_path, "r:gz") as tar:
                print(f"Untar downloaded tar.gz to {self.local_base_dir}")
                tar.extractall(self.local_base_dir)
                if os.path.exists(dataset_dir_path):
                    print(f"dataset created and available at {dataset_dir_path}")
                else:
                    print(f"Error: Unable to extract the tar file, it does not exist at {dataset_dir_path}")
                    return self.local_base_dir
                self.change_permissions(dataset_dir_path)
        return self.local_base_dir

    def set_dataset_paths(self):
        """
        Downloads all necessary dataset files and initiate all the paths for
        further use.

        Args:

        Returns:
                True if everything is good False to indicate something gone
                wrong
        """
        print("Setting necessary paths for the dataset")
        self.dataset_path = self.download_dataset()
        if not os.path.exists(self.dataset_path):
            print("Dataset Dir {self.dataset_path} does not exist")
            return False

        self.train_dataset_filepath = os.path.join(
            self.dataset_path, self.dataset_name, self.dataset_name + "_base.fvecs"
        )
        if not os.path.exists(self.train_dataset_filepath):
            print("Train dataset filepath {self.train_dataset_filepath} does not exist")
            return False

        self.query_dataset_filepath = os.path.join(
            self.dataset_path, self.dataset_name, self.dataset_name + "_query.fvecs"
        )
        if not os.path.exists(self.query_dataset_filepath):
            print("Query dataset filepath {self.query_dataset_filepath} does not exist")
            return False

        self.learn_dataset_filepath = os.path.join(
            self.dataset_path, self.dataset_name, self.dataset_name + "_learn.fvecs"
        )
        if not os.path.exists(self.learn_dataset_filepath):
            print("Learn dataset filepath {self.learn_dataset_filepath} does not exist")
            return False

        self.groundtruth_dataset_filepath = os.path.join(
            self.dataset_path,
            self.dataset_name,
            self.dataset_name + "_groundtruth.ivecs",
        )
        if not os.path.exists(self.groundtruth_dataset_filepath):
            print(
                "Groundtruth dataset filepath {self.groundtruth_dataset_filepath} does not exist"
            )
            return False

        return True

    def validate_dataset(self):
        """
        Check for required files to exist in the dataset dir. This to be called
        only after set_dataset_paths. Dataset dir will have fillowing files
        sift*_query.fvecs sift*_learn.fvecs sift*_groundtruth.ivecs
        sift*_base.fvecs

        Args:

        Returns:
        """
        print(f"Validating dataset at dir {self.dataset_path}")
        file_patterns_to_check = [
            "sift.*_query.fvecs",
            "sift.*_learn.fvecs",
            "sift.*_groundtruth.ivecs",
            "sift.*_base.fvecs",
        ]
        missing_patterns = []
        all_available_files = glob.glob(
            os.path.join(self.dataset_path, self.dataset_name, "*vecs")
        )
        all_available_files = [os.path.basename(file) for file in all_available_files]
        print(f"All file names in dir {all_available_files}")
        # Get all files in dataset dir and check for each file existence in the
        # list.
        for each_pattern in file_patterns_to_check:
            regex_pattern = re.compile(each_pattern)
            file_found = False
            for file_name in all_available_files:
                if regex_pattern.match(file_name):
                    print(
                        f" Success Matched file {file_name} with pattern {each_pattern}"
                    )
                    file_found = True
                    break
            if not file_found:
                # print(f"Missing file {file_name} with pattern {each_pattern}")
                missing_patterns.append(each_pattern)

        if missing_patterns:
            print(
                f"Files missing with pattern {missing_patterns} in dataset dir:{self.dataset_path}"
            )
            return False

        print(
            f"Successfull Validation of dataset with name {self.dataset_name}"
            f" at {os.path.join(self.dataset_path, self.dataset_name)}"
        )
        return True

    def extract_vectors_from_file(self, use_hdf5_datasets, type_of_vec="train", batch_size=0):
        """
        Extracts the vectors either from tar.gz files or from hdf5 files based
        use_hdf5_datasets Initialize the necessary vector datastructures as
        follows
            - train_vecs
            - query_vecs
            - neighbors_vecs
            - distances_vecs - Gets initialized only when "use_hdf5_datasets"
              used.
        Args:
            param1 (str) : use_hdf5_datasets True or False

        Returns:
            numpy.ndarray : Vectors read from the file
        """

        self.set_dataset_paths()
        if use_hdf5_datasets:
            print(f"Extracting needed vectors of type: {type_of_vec} from hdf5 files for dataset {self.dataset_name}")
            ds_error = self.extract_vectors_using_hdf5_files(self.dataset_name, type_of_vec)
            if ds_error != "":
                print(f"Error: Could not extract vectors from hdf5 file for dataset: {self.dataset_name}")
            else:
                print(f"{type_of_vec} vectors are initialized")

            yield 0
        else:
            print(f"Extracting needed vectors of type: {type_of_vec} from tar.gz files for dataset {self.dataset_name}")
            filepath = ""
            out_vector = None
            vector_types = ["train", "query", "learn", "groundtruth"]
            if type_of_vec == "train":
                filepath = self.train_dataset_filepath
            elif type_of_vec == "query":
                filepath = self.query_dataset_filepath
            elif type_of_vec == "learn":
                filepath = self.learn_dataset_filepath
            elif type_of_vec == "groundtruth":
                filepath = self.groundtruth_dataset_filepath
            try:
                if type_of_vec != "groundtruth":
                    with open(
                            filepath, "rb"
                    ) as file:  # Open the file in binary mode to read the data from the fvec/ivec/bvec files.
                        (dimension,) = struct.unpack(
                            "i", file.read(4)
                        )
                        print(f"Dimension of the vector type {type_of_vec} is :{dimension}")
                        # First 4bytes denote dimension of the vector. Next
                        # bytes of size "dimension" number of 4bytes will
                        # give us the full vector.
                        num_vectors = os.path.getsize(filepath) // (4 + 4 * dimension)

                        if batch_size == 0:
                            batch_size = num_vectors
                        num_batches = num_vectors // batch_size
                        print(
                            f"Total number of vectors in {type_of_vec} dataset: {num_vectors}"
                        )
                        print(f"Total number of batches of size {batch_size}: {num_batches}")

                        file.seek(0)  # move the cursor back to first position to start with first vector.

                        for j in range(num_batches):
                            out_vector = np.zeros(
                            (batch_size, dimension)
                            )

                            for i in range(batch_size):
                                file.read(
                                    4
                                )  # To move cursor by 4 bytes to ignore dimension of the vector.
                                # Read float values of size 4bytes of length "dimension"
                                out_vector[i] = struct.unpack(
                                    "f" * dimension, file.read(dimension * 4)
                                )

                            if type_of_vec == "train":
                                self.train_vecs = out_vector
                                self.num_train_vecs = num_vectors
                            if type_of_vec == "query":
                                self.query_vecs = out_vector
                                self.num_query_vecs = num_vectors
                            if type_of_vec == "learn":
                                self.learn_vecs = out_vector
                                self.num_learn_vecs = num_vectors
                            print(f"{type_of_vec} vectors are initialized")
                            print(f"Shape of initialized vectors: {self.train_vecs.shape}")

                            yield j
                else:
                    # For "groundtruth" vector data dataformat is different.
                    # Vector values are integers of train vectors.
                    print("Extracting vectors from groundtruth files which have train vector ids as neighbors")
                    total_file_size = os.path.getsize(filepath)
                    number_of_vectors = total_file_size // (4 + 4 * 100)
                    print(f"total_file_size:{total_file_size}, number_of_vectors:{number_of_vectors}")
                    with open(
                            filepath, "rb"
                    ) as file:
                        out_vector = np.zeros(
                            (100, 100)
                        )
                        for i in range(5):
                            file.read(
                                4
                            )  # To move cursor by 4 bytes to ignore dimension of the vector.
                            out_vector[i] = struct.unpack(
                                "i" * 100, file.read(100 * 4)
                            )
                            print(
                                f"First 100 neighours using Squared Eucleadean distance in increasing order:{out_vector[i]}")
                    self.neighbors_vecs = out_vector
                    self.num_neighbors_vecs = number_of_vectors
                    print(f"{type_of_vec} vectors are initialized")

                    yield 0

            except FileNotFoundError:
                print(f"Error: File '{filepath}' not found.")
            except Exception as e:
                print(f"Error: An error occurred while extracting train vectors: {str(e)}")

    def change_permissions(self, directory_path):
        """
        Args:
            param1 (str) : directory_path
        """
        try:
            # Set read and write permissions for the owner, group, and others
            os.chmod(
                directory_path, 0o777
            )  # 0o777 corresponds to read, write, and execute for everyone

            print(f"Permissions changed successfully for {directory_path}")
        except Exception as e:
            print(f"Error: Error occurred while changing permissions: {str(e)}")

    def extract_vectors_using_hdf5_files(self, dataset_name, type_of_vec="train"):
        """_summary_

        Args:
            dataset_name (str): dataset name
            type_of_vec (str, optional): train or query or neightbors or distances . Defaults to "train"

        Returns:
             str: Empty string on successfull extraction of data from hdf5 files.
        """
        supported_datasets = HDF5_FORMATTED_DATASETS.keys()
        if dataset_name in supported_datasets:
            # URL of the HDF5 file url =
            # "http://ann-benchmarks.com/sift-128-euclidean.hdf5"
            url = HDF5_FORMATTED_DATASETS[dataset_name]["url"]
            local_file_path = HDF5_FORMATTED_DATASETS[dataset_name]["local_file_path"]

            # download the dataset if local does not exist.
            if not os.path.exists(local_file_path):
                # Create dir path if does not exist.
                directory_path = os.path.dirname(local_file_path)
                os.makedirs(directory_path, exist_ok=True)
                # Download the HDF5 file
                print(f"Downloading dataset using url {url} to {local_file_path}")
                urlretrieve(url, local_file_path)

            # Open the HDF5 file.
            with h5py.File(local_file_path, "r") as hdf_file:
                # Dataset has following types of the data.
                # train, query, neighbors and distances
                [print(f"Hdf file {local_file_path} has following data : {keys}") for keys in hdf_file]

                if type_of_vec == "train":
                    # Dealing with train dataset
                    train_dataset = hdf_file["train"]
                    # Convert dataset to NumPy array
                    self.train_vecs = np.array(train_dataset)
                    # Print the shape of the array
                    print("Shape of the train dataset:", self.train_vecs.shape)
                    print("First 5 elements train_data:", self.train_vecs[:5])

                if type_of_vec == "query":
                    # Dealing with test dataset
                    test_dataset = hdf_file["test"]
                    # Convert dataset to NumPy array
                    self.query_vecs = np.array(test_dataset)
                    # Print the shape of the array
                    print("Shape of the test dataset:", self.query_vecs.shape)
                    print("First 5 elements test_data:", self.query_vecs[:5])

                if type_of_vec == "neighbors":
                    # Dealing with test neighbours
                    neighbors_dataset = hdf_file["neighbors"]
                    # Convert dataset to NumPy array
                    self.neighbors_vecs = np.array(neighbors_dataset)
                    # Print the shape of the array
                    print("Shape of the neighbors dataset:", self.neighbors_vecs.shape)
                    print("First 5 elements neighbors_data:", self.neighbors_vecs[:5])

                if type_of_vec == "distances":
                    # Dealing with test distances
                    distances_dataset = hdf_file["distances"]
                    # Convert dataset to NumPy array
                    self.distances_vecs = np.array(distances_dataset)
                    # Print the shape of the array
                    print("Shape of the distances dataset:", self.distances_vecs.shape)
                    print("First 5 elements distances_data:", self.distances_vecs[:5])
                return ""
        else:
            print(f"Error: dataset name {dataset_name} is not supported")
            return "Error: dataset name" + dataset_name + "is not supported"

class DocKey:
    def __init__(self, prefix="", start=0):
        self.start_key = start
        self.counter = start
        self.prefix = prefix
        self.key_lock = threading.Lock()

    def get_next_key(self):
        with self.key_lock:
            self.counter += 1
            # Adding 1 to counter because of the way cbimport works.
            # cmbimport MONOINCR start from 1
            doc_key = self.prefix + str(self.counter + 1)
            return doc_key, self.counter

    def get_key(self, doc_index):
        # Adding 1 to doc_index because of the way cbimport works.
        # cmbimport MONOINCR start from 1
        doc_key = self.prefix + str(doc_index + 1 + self.start_key)
        return doc_key

    def get_current_index(self):
        with self.key_lock:
            return self.counter

def get_json_body(doc_key_gen, vector):
    id, sno = doc_key_gen.get_next_key()
    sname = number_to_alphabetic(sno)
    data_record = {
        "sno": sno,
        "sname": sname,
        "id": id,
        "dim": len(vector.tolist()),
        "vector_data": vector.tolist()
    }
    return data_record

########################################################################################
# Func to upsert vector to couchbase collection.
def upsert_vector(collection, doc_key_gen, vector, dataset_name):
    id, sno = doc_key_gen.get_next_key()
    sname = number_to_alphabetic(sno)
    data_record = {
        "sno": sno,
        "sname": sname,
        "id": id,
        "dim": len(vector.tolist()),
        "vector_data": vector.tolist()
    }

    last_print_time = time.time()
    for retry in range(3):
        try:
            elapsed_time = time.time() - last_print_time
            if elapsed_time >= 0:
                print(f"From dataset {dataset_name} Uploading vector no: {sno} with ID: {id} to {collection.name}")
                last_print_time = time.time()
            collection.upsert(id, data_record)
        except Exception as e:
            print(f"{e} Error uploading vector no: {sno} with id: {id} to collection: {collection.name}")
            retry += 1
            print(f"{e} Retrying after 1sec.. {retry} {id}")
            time.sleep(5)
    return data_record

def update_doc_vector(collection, doc_key_gen, doc_index, vector, dataset_name):
    last_print_time = time.time()
    doc_key = doc_key_gen.get_key(doc_index)
    id = doc_key
    sno = doc_index
    sname = number_to_alphabetic(sno)
    data_record = {
        "sno": sno,
        "sname": sname,
        "id": id,
        "dim": len(vector.tolist()),
        "vector_data": vector.tolist()
    }
    for retry in range(3):
        try:
            elapsed_time = time.time() - last_print_time
            if elapsed_time >= 0:
                print(f"From dataset {dataset_name} Updating vector no: {doc_index} with ID: {id} in {collection.name}" \
                      f" with vector of length {len(vector)}")
                last_print_time = time.time()
            collection.upsert(id, data_record)
        except Exception as e:
            print(f"{e} Error uploading vector no: {doc_index} with id: {id} to collection: {collection.name}")
            retry += 1
            print(f"{e} Retrying after 1sec.. {retry} {id}")
            time.sleep(5)
    return data_record


def number_to_alphabetic(n):
    """Gives the alphabet equivalent to the number mentioned.

    Args:
        n (int): number

    Returns:
        _type_: _description_
    """
    result = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(remainder + ord('a')) + result
    return result

def execute_command(command, hostname, ssh_username, ssh_password):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname, username=ssh_username, password=ssh_password,
                timeout=120, banner_timeout=120)

    channel = ssh.get_transport().open_session()
    channel.get_pty()
    channel.settimeout(900)
    stdin = channel.makefile('wb')
    stdout = channel.makefile('rb')
    stderro = channel.makefile_stderr('rb')

    channel.exec_command(command)
    data = channel.recv(1024)
    temp = ""
    while data:
        temp += str(data)
        data = channel.recv(1024)
    channel.close()
    stdin.close()

    output = []
    error = []
    for line in stdout.read().splitlines():
        if "No such file or directory" not in line:
            output.append(line)
    for line in stderro.read().splitlines():
        error.append(line)
    if temp:
        line = temp.splitlines()
        output.extend(line)
    stdout.close()
    stderro.close()

    ssh.close()
    return output, error

def move_file_to_remote(local_path, remote_path, hostname, username, password):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname, username=username, password=password,
                timeout=120, banner_timeout=120)
    sftp = ssh.open_sftp()
    print(local_path, remote_path)
    sftp.put(local_path, remote_path)
    sftp.close()
    ssh.close()
    print(f"File '{local_path}' successfully moved to '{remote_path}' on the remote server.")

########################################################################################

class CouchbaseOps:
    """
        CouchbaseOps provides a way to
        - Create necessary buckets, scopes and
        collectionreate data into couchbase collection
        - Create fts index on vector data fields using supported index types
        - Retrieve documents based on the index query.
    """
    couchbase_endpoint_ip = ""
    username = ""
    password = ""
    dataset_name = ""
    prefix_for_buckets = ""
    bucket_name = ""
    scope_name = ""
    collection_name = ""

    def __init__(
            self,
            couchbase_endpoint_ip,
            username="Administrator",
            password="password",
            dataset_name="sift",
            bucket_name="",
            scope_name="",
            collection_name="",
            capella_run=False,
            cbs=False,
            cbimport=False,
            doc_key_generator=None,
            batch_size=0,
            faiss_index_names=None,
            faiss_node="172.23.120.96",
            slave_ip="172.23.105.211"
    ):
        self.couchbase_endpoint_ip = couchbase_endpoint_ip
        self.username = username
        self.password = password
        self.dataset_name = dataset_name
        self.prefix_for_buckets = "VS"
        if bucket_name == "":
            self.bucket_name = (
                    self.prefix_for_buckets + "_vector_bucket_" + self.dataset_name.upper()
            )
        else:
            self.bucket_name = bucket_name
        if scope_name == "":
            self.scope_name = self.prefix_for_buckets + "_vector_scope_" + self.dataset_name.upper()
        else:
            self.scope_name = scope_name

        if collection_name == "":
            self.collection_name = (
                    self.prefix_for_buckets + "_vector_collection_" + self.dataset_name.upper()
            )
        else:
            self.collection_name = collection_name
        self.capella_run = capella_run
        self.cbs = cbs
        self.cbimport = cbimport
        self.doc_key_gen = doc_key_generator
        if not self.doc_key_gen:
            self.doc_key_gen = DocKey()
        self.batch_size = batch_size
        self.faiss_index_names = None
        if faiss_index_names:
            self.faiss_indexes = []
            self.faiss_index_names = faiss_index_names
        else:
            self.faiss_indexes = None
        self.faiss_node = faiss_node
        self.slave_ip = slave_ip

        print("Faiss indexes: {}".format(self.faiss_indexes))

    def create_bucket(self, cluster):
        bucket_manager = cluster.buckets()
        try:
            print("Creating bucket: {}".format(self.bucket_name))
            bucket_manager.create_bucket(
                CreateBucketSettings(
                    name=self.bucket_name,
                    flush_enabled=True,
                    ram_quota_mb=100,
                    num_replicas=0,
                    conflict_resolution_type=ConflictResolutionType.SEQUENCE_NUMBER,
                    bucket_type=BucketType.COUCHBASE))
        except BucketAlreadyExistsException:
            print("Bucket: {} already exists. So not creating it again".format(self.bucket_name))

    def create_scope(self):
        url = f"http://{self.couchbase_endpoint_ip}:8091/pools/default/buckets/{self.bucket_name}/scopes"
        data = {"name": self.scope_name}

        print(url)
        print(data)
        response = requests.post(url, auth=(self.username, self.password), json=data)

        if response.status_code == 200:
            print(f"Scope '{self.scope_name}' created successfully.")
        else:
            print(
                f"Failed to create scope. Status code: {response.status_code}, Response: {response.text}")

    def create_collection(self):
        url = f"http://{self.couchbase_endpoint_ip}:8091/pools/default/buckets/{self.bucket_name}/scopes/{self.scope_name}/collections"
        data = {"name": self.collection_name}
        print(url)
        print(data)
        response = requests.post(url, auth=(self.username, self.password), json=data)

        if response.status_code == 200:
            print(f"Collection '{self.collection_name}' created successfully.")
        else:
            print(
                f"Failed to create collection. Status code: {response.status_code}, Response: {response.text}")

    def create_bucket_scope_collection(self, cluster, couchbase_endpoint):
        """
        Creates couchbase bucket, scope and collection

        Returns:
            couchbase collection object
        """

        print(f"Creating bucket on {couchbase_endpoint} with bucket name:{self.bucket_name}")
        self.create_bucket(cluster)
        time.sleep(5)
        bucket = cluster.bucket(self.bucket_name)

        coll_manager = bucket.collections()
        try:
            print(f"Creating scope in bucket:{self.bucket_name} with scope name:{self.scope_name}")
            coll_manager.create_scope(self.scope_name)
            time.sleep(5)
        except ScopeAlreadyExistsException as e:
            print(f"Scope with name {self.scope_name} exists already, skipping creation again")
        except Exception as e:
            print(f"Scope Creation failed, collection name: {self.scope_name}")
            return

        collection_spec = CollectionSpec(
            self.collection_name,
            scope_name=self.scope_name)

        try:
            print(f"Creating collection in scope:{self.scope_name} with collection name:{self.collection_name}")
            collection = coll_manager.create_collection(collection_spec)
            time.sleep(5)
        except CollectionAlreadyExistsException as ex:
            print(f"Collection with name {self.collection_name} exists already, skipping creation again")
        except Exception as e:
            print(f"Error: Collection Creation failed, collection name: {self.collection_name}")
        time.sleep(10)
        collection = bucket.scope(self.scope_name).collection(self.collection_name)
        return collection

    def update_vector_dimension(self, vector, current_dim, dim):
        # Resize the vector to the desired dimension
        if current_dim < dim:
            # If the current dimension is less than the desired dimension, repeat the values
            repeat_values = dim - current_dim
            repeated_values = np.tile(vector, ((dim + current_dim - 1) // current_dim))
            return repeated_values[:dim]
        elif current_dim > dim:
            # If the current dimension is greater than the desired dimension, truncate the vector
            return vector[:dim]

    def update_vector(self, vector, perturbation_range = 1):
        num_changes = np.random.randint(1, len(vector) + 1)
        indices_to_change = np.random.choice(len(vector), num_changes, replace=False)

        for index_to_change in indices_to_change:
            perturbation = np.random.uniform(-perturbation_range, perturbation_range)
            new_value = vector[index_to_change] + perturbation

            vector[index_to_change] = new_value

        return vector

    def upsert(self, dims = [], percentages = [], iterations=1, update=False, current_dims = []):
        """
        Dumps train vectors into Couchbase collection which is created
        automatically

        Args:
            use_hdf5_datasets (bool, optional): To choose tar.gz or hdf5 files .
            Defaults to False.
        """
        auth = PasswordAuthenticator(self.username, self.password)
        if not self.capella_run:
            couchbase_endpoint = "couchbase://" + self.couchbase_endpoint_ip
            cluster = Cluster(couchbase_endpoint, ClusterOptions(auth))
        else:
            timeout_options = ClusterTimeoutOptions(kv_timeout=timedelta(seconds=120),
                                                    query_timeout=timedelta(seconds=10))
            options = ClusterOptions(PasswordAuthenticator(self.username, self.password),
                                     timeout_options=timeout_options)
            cluster = Cluster('couchbases://' + self.couchbase_endpoint_ip + '?ssl=no_verify',
                              options)
            couchbase_endpoint = f"couchbases://{self.couchbase_endpoint_ip}"

        print(
            f"user:{self.username} pass: {self.password} endpoint: {couchbase_endpoint} bucket_name: {self.bucket_name} {self.scope_name}   {self.collection_name} "
        )

        # create Bucket, Scope and Collection.
        if self.cbs:
            time.sleep(10)
            collection = self.create_bucket_scope_collection(cluster, couchbase_endpoint)
            if collection is None:
                print(f"Error: collection object cannot be None")
                return
        else:
            bucket = cluster.bucket(self.bucket_name)
            collection = bucket.scope(self.scope_name).collection(self.collection_name)

        # initialize the needed vectors.
        ds = VectorDataset(self.dataset_name)
        use_hdf5_datasets = True
        if self.dataset_name in ds.supported_sift_datasets:
            use_hdf5_datasets = False

        if self.faiss_index_names:

            for i in range(0, len(self.faiss_index_names)):
                if i >= len(dims):
                    print(f"Creating faiss index with dimension {ds.sift_dataset_dims[self.dataset_name]}")
                    self.faiss_indexes.append(faiss.IndexFlatL2(ds.sift_dataset_dims[self.dataset_name]))
                else:
                    print(f"Creating faiss index with dimension {dims[i]}")
                    self.faiss_indexes.append(faiss.IndexFlatL2(dims[i]))

            default_dim_faiss_index = None
            if len(self.faiss_index_names) > len(dims):
                default_dim_faiss_index = self.faiss_indexes[len(dims)]

        dataset_generator = ds.extract_vectors_from_file(use_hdf5_datasets, type_of_vec="train", batch_size=self.batch_size)

        for batch in dataset_generator:

            # dump train vectors into couchbase collection in vector data
            # type fomat.
            print(f"Processing batch no. {batch}")
            if ds.train_vecs is not None:

                total_vectors = len(ds.train_vecs)

                # Get random indices for vectors to resize
                indices_to_resize = list(range(total_vectors))
                indices_to_update = indices_to_resize.copy()

                # if len(percentages) != len(dims):
                #     raise ValueError("percentages and dims lists must have the same length")

                total_percentage = 0
                for per in percentages:
                    total_percentage += per

                if total_percentage > 1:
                    raise ValueError("Total percentage of docs to update should be less than 1")

                if len(dims) > 0:

                    changed_indices = []
                    for idx, (percentage, dim) in enumerate(zip(percentages, dims)):
                        vectors_to_resize = int(percentage * total_vectors)

                        current_indices = indices_to_resize[:vectors_to_resize]
                        indices_to_resize = indices_to_resize[vectors_to_resize:]
                        ds.train_vecs = list(ds.train_vecs)
                        # print("Number of docs resized with dimension {} is {}".format(dim, len(current_indices)))

                        if self.faiss_index_names:
                            faiss_index = self.faiss_indexes[idx]


                        for index in current_indices:

                            vector = ds.train_vecs[index]
                            current_dim = len(vector)

                            updated_vector = self.update_vector_dimension(vector, current_dim, dim)
                            ds.train_vecs[index] = updated_vector

                            if self.faiss_index_names:
                                index_vector = np.array([updated_vector]).astype('float32')
                                faiss.normalize_L2(index_vector)
                                faiss_index.add(index_vector)

                        changed_indices += current_indices

                    if self.faiss_index_names:
                        if default_dim_faiss_index:
                            default_dim_vectors = [vector for i, vector in enumerate(ds.train_vecs) if i not in changed_indices]
                            index_vectors = np.array(default_dim_vectors).astype('float32')
                            faiss.normalize_L2(index_vectors)
                            default_dim_faiss_index.add(index_vectors)

                elif update and (len(current_dims) == 0):
                    for idx, percentage in enumerate(percentages):
                        vectors_to_resize = int(percentage * total_vectors)

                        current_indices = indices_to_resize[:vectors_to_resize]
                        indices_to_resize = indices_to_resize[vectors_to_resize:]
                        ds.train_vecs = list(ds.train_vecs)

                        if self.faiss_index_names:
                            faiss_index = default_dim_faiss_index

                        for index in current_indices:
                            vector = ds.train_vecs[index]
                            # print(f"Changing values for vector {index}")
                            updated_vector = self.update_vector(vector)
                            ds.train_vecs[index] = updated_vector


                    if self.faiss_index_names:
                        index_vectors = np.array(ds.train_vecs).astype('float32')
                        faiss.normalize_L2(index_vectors)
                        faiss_index.add(index_vectors)

                elif update and len(current_dims) > 0:

                    for idx, (percentage, dim) in enumerate(zip(percentages, current_dims)):
                        vectors_to_resize = int(percentage * total_vectors)

                        current_indices = indices_to_resize[:vectors_to_resize]
                        indices_to_resize = indices_to_resize[vectors_to_resize:]
                        ds.train_vecs = list(ds.train_vecs)
                        # print("Number of docs resized with dimension {} is {}".format(dim, len(current_indices)))

                        for index in current_indices:

                            vector = ds.train_vecs[index]
                            current_dim = len(vector)

                            updated_vector = self.update_vector_dimension(vector, current_dim, dim)
                            updated_vector = self.update_vector(updated_vector)
                            ds.train_vecs[index] = updated_vector

            if ds.train_vecs is not None and len(ds.train_vecs) > 0:
                if not self.cbimport:
                    if not update:
                        print(f"Spawning {MAX_THREADS} threads to speedup the upsert.")
                        with concurrent.futures.ThreadPoolExecutor(MAX_THREADS) as executor:
                            upsert_partial = partial(upsert_vector, collection, dataset_name=self.dataset_name)
                            futures = {executor.submit(upsert_partial, self.doc_key_gen, d): d for counter, d in
                                    enumerate(ds.train_vecs, start=1)}
                            for future in concurrent.futures.as_completed(futures):
                                try:
                                    future.result()
                                except Exception as e:
                                    print(f"Error: {e}")
                    else:
                        for percentage in percentages:
                            vectors_to_resize = int(percentage * total_vectors)

                            current_indices = indices_to_update[:vectors_to_resize]
                            indices_to_update = indices_to_update[vectors_to_resize:]
                            with concurrent.futures.ThreadPoolExecutor(MAX_THREADS) as executor:
                                upsert_partial = partial(update_doc_vector, collection, dataset_name=self.dataset_name)
                                futures = {executor.submit(upsert_partial, self.doc_key_gen, (batch * self.batch_size + d), ds.train_vecs[d]): ds.train_vecs[d] for counter, d in
                                        enumerate(current_indices, start=0)}
                                for future in concurrent.futures.as_completed(futures):
                                    try:
                                        future.result()
                                    except Exception as e:
                                        print(f"Error: {e}")


                else:
                    filename = f"{uuid.uuid4().hex}.json"
                    with open(filename, "w") as json_file:
                        for counter, d in enumerate(ds.train_vecs, start=1):
                            json_obj = json.dumps(get_json_body(self.doc_key_gen, d))
                            json_file.write(json_obj + "\n")

                    hostname = self.couchbase_endpoint_ip
                    node_ip = self.couchbase_endpoint_ip
                    if self.capella_run:
                        hostname = f"couchbases://{self.couchbase_endpoint_ip}"
                        node_ip = self.slave_ip

                    move_file_to_remote(os.getcwd() + "/" + filename, "/tmp/" + filename, node_ip, "root", "couchbase")
                    num_items = ds.num_train_vecs
                    num_batch_items = len(ds.train_vecs)
                    for i in range(iterations):
                        key_offset = (i * num_items) + 1 + (batch * num_batch_items) + self.doc_key_gen.start_key
                        key_str = f'{self.doc_key_gen.prefix}#MONO_INCR[{key_offset}]#'
                        cbimport_command = f"/opt/couchbase/bin/cbimport json --cluster {hostname} --bucket {self.bucket_name} " \
                                f"--dataset /tmp/{filename} --format lines --username {self.username} --password {self.password} " \
                                f"--scope-collection-exp '{self.scope_name}.{self.collection_name}' --generate-key '{key_str}' " \
                                f"--no-ssl-verify"
                        stdout, stderr = execute_command(cbimport_command, node_ip, "root", "couchbase")
                        print(stdout, stderr)

                    rm_file_command = f"rm -f /tmp/{filename}"
                    execute_command(rm_file_command, node_ip, "root", "couchbase")
            else:
                print("Error: train vectors data structure is empty, please check the dataset")

        if self.faiss_index_names:
            node_ip = self.faiss_node
            print("Node IP: {}".format(node_ip))
            for idx, index in enumerate(self.faiss_indexes):
                index_file = self.faiss_index_names[idx] + ".index"
                print("Length of faiss index: {}".format(index.ntotal))
                faiss.write_index(index, index_file)
                move_file_to_remote(os.getcwd() + "/" + index_file, "/tmp/" + index_file, node_ip, "root", "couchbase")

class VectorLoader:

    def __init__(self):
        parser = argparse.ArgumentParser()
        valid_choices = ["fashion-mnist", "mnist", "gist"]
        parser.add_argument("-n", "--node", help="Couchbase Server Node Address/ host", required=True)
        parser.add_argument("-u", "--username", help="Couchbase Server Cluster Username", required=True)
        parser.add_argument("-p", "--password", help="Couchbase Server Cluster Password", required=True)
        parser.add_argument("-b", "--bucket", help="Bucket name on which indexes are to be created", default="")
        parser.add_argument("-sc", "--scope", help="Scope name on which indexes are to be created", default="")
        parser.add_argument("-coll", "--collection", help="Collection name on which indexes are to be created",
                            default="")
        parser.add_argument("-ds", "--dataset", help=f"Choose one of: {', '.join(valid_choices)}",
                            default=valid_choices)
        parser.add_argument("-c", "--capella", default=False)
        parser.add_argument("-cbs", "--create_bucket_structure", default=True)
        parser.add_argument("-per", "--percentages_to_resize", nargs='*', type=float, default=[])
        parser.add_argument("-dims", "--dimensions_for_resize", nargs='*', type=int, default=[])
        parser.add_argument("-curr_dims", "--current_dimensions", nargs='*', type=int, default=[])
        parser.add_argument("-i", "--cbimport", help="Use cbimport to load documents", default=False)
        parser.add_argument("-iter", "--iterations", help="Number of iterations of cbimport to run", type=int, default=1)
        parser.add_argument("-update", "--update_docs", default=False)
        parser.add_argument("-bs", "--batch_size", help="Batch size(in term of number of docs)", type=int, default=0)
        parser.add_argument("-indexes", "--faiss_indexes",  nargs='*', type=str, default=None)
        parser.add_argument("-fn", "--faiss_node", help="Faiss Node Address where faiss indexes will be created", default="")
        parser.add_argument("-slave_ip", "--slave_ip", help="Faiss Node Address where faiss indexes will be created", default="172.23.105.211")
        parser.add_argument("-sk", "--start_key", help="Start index for doc Id's", type=int, default=0)

        args = parser.parse_args()
        self.node = args.node
        self.username = args.username
        self.password = args.password
        self.bucket = args.bucket
        self.dataset = args.dataset
        if not isinstance(self.dataset, list):
            self.dataset = [self.dataset]
        self.scope = args.scope
        self.collection = args.collection
        self.cbimport = args.cbimport
        self.capella_run = args.capella
        self.dim_for_resize = args.dimensions_for_resize
        self.curr_dims = args.current_dimensions
        self.percentage_to_resize = args.percentages_to_resize
        self.iterations = args.iterations
        self.batch_size = args.batch_size
        self.faiss_indexes = args.faiss_indexes
        self.faiss_node = args.faiss_node
        self.slave_ip = args.slave_ip
        self.start_key = args.start_key
        print("Iterations: {}".format(self.iterations))
        print("Batch size: {}".format(self.batch_size))
        print("dims to resize: {}".format(self.dim_for_resize))
        print("perc to resize: {}".format(self.percentage_to_resize))
        print("Faiss indexes to create: {}".format(self.faiss_indexes))
        if self.capella_run == 'True' or self.capella_run == 'true':
            self.capella_run = True
        else:
            self.capella_run = False
        self.cbs = args.create_bucket_structure
        if self.cbs == 'True' or self.cbs == 'true':
            self.cbs = True
        else:
            self.cbs = False
        self.update = args.update_docs
        if self.update == 'True' or self.update == 'true':
            self.update = True
        else:
            self.update = False

    def fetch_rest_url(self, url):

        """
        meant to find the srv record for Capella runs
        """
        print("This is a Capella run. Finding the srv domain for {}".format(url))
        srv_info = {}
        srv_records = dns.resolver.query('_couchbases._tcp.' + url, 'SRV')
        for srv in srv_records:
            srv_info['host'] = str(srv.target).rstrip('.')
            srv_info['port'] = srv.port
        print("This is a Capella run. Srv info {}".format(srv_info))
        return srv_info['host']

    def load_data(self):
        if self.capella_run and self.cbs:
            print("creating bucket isn't allowed with capella clusters using SDK, aborting")
            return
        for dataset_name in self.dataset:
            cbops = CouchbaseOps(
                couchbase_endpoint_ip=self.node, username=self.username, password=self.password,
                bucket_name=self.bucket,
                dataset_name=dataset_name,
                scope_name=self.scope, collection_name=self.collection,
                capella_run=self.capella_run,
                cbs=self.cbs,
                cbimport=self.cbimport,
                doc_key_generator=DocKey("vect", start=self.start_key),
                batch_size=self.batch_size,
                faiss_index_names=self.faiss_indexes,
                faiss_node=self.faiss_node,
                slave_ip=self.slave_ip
            )

            cbops.upsert(dims=self.dim_for_resize, percentages=self.percentage_to_resize,
                         iterations=self.iterations, update=self.update, current_dims=self.curr_dims)
            break


if __name__ == '__main__':
    vl = VectorLoader()
    vl.load_data()

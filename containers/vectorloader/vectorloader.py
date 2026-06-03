#!/usr/bin/env python3
"""
High-throughput vector embedding loader for Couchbase.

Reads embeddings from a CSR binary file and upserts them into existing documents
in a Couchbase bucket/scope/collection. Documents are processed in key-ascending order
to match the row order in the embeddings file.

Embedding format written to each doc:
    "embedding": [[indices...], [values...]]

Features:
    - Loads embeddings from CSR files into Couchbase documents
    - Auto-selects file based on --num-docs:
        * <= 100,000: base_small.csr
        * <= 1,000,000: base_1M.csr
        * > 1,000,000 or omitted: base_full.csr
    - --base64: Base64 encodes the embedding vector before storage
    - --xattrs: Stores embedding in extended attributes (xattrs) instead of document body
    - --concurrency: Controls parallel operations (default: 100)
    - Handles count mismatches gracefully: processes minimum of (docs, embeddings)
    - Detailed logging with -v (errors) and -vv (debug)

Usage:
    docker run --rm -v /path/to/embeddings:/app/embeddings vl \
        --connstr couchbase://host \
        --username Administrator --password password \
        --bucket mybucket --scope _default --collection _default \
        --num-docs 100000

    # With base64 encoding
    docker run --rm -v /path/to/embeddings:/app/embeddings vl \
        --connstr couchbase://host \
        --username Administrator --password password \
        --bucket mybucket --scope _default --collection _default \
        --num-docs 100000 --base64

    # With xattrs storage
    docker run --rm -v /path/to/embeddings:/app/embeddings vl \
        --connstr couchbase://host \
        --username Administrator --password password \
        --bucket mybucket --scope _default --collection _default \
        --num-docs 100000 --xattrs

    # With both base64 and xattrs
    docker run --rm -v /path/to/embeddings:/app/embeddings vl \
        --connstr couchbase://host \
        --username Administrator --password password \
        --bucket mybucket --scope _default --collection _default \
        --num-docs 100000 --base64 --xattrs
"""

import argparse
import asyncio
import struct
import time
import sys
import os
import traceback
import logging
import json
import base64
from datetime import timedelta
from typing import Optional, Iterator, Tuple, List, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger(__name__)

# Hardcoded embeddings directory (inside container)
EMBEDDINGS_DIR = "/app/embeddings"

# File mapping based on num_docs
EMBEDDING_FILES = {
    100000: "base_small.csr",     # Small dataset (up to 100K)
    1000000: "base_1M.csr",      # 1M documents
    -1: "base_full.csr",         # Full dataset
}


def select_embeddings_file(num_docs: Optional[int]) -> str:
    """
    Select the appropriate embeddings file based on num_docs.
    
    Args:
        num_docs: Number of documents (100000, 1000000, or None for full)
        
    Returns:
        Full path to the embeddings file
    """
    log.info(f"Selecting embeddings file for num_docs={num_docs}")
    
    # List available files in embeddings directory
    if os.path.exists(EMBEDDINGS_DIR):
        files = os.listdir(EMBEDDINGS_DIR)
        log.info(f"Available files in {EMBEDDINGS_DIR}: {files}")
    else:
        log.error(f"Embeddings directory does not exist: {EMBEDDINGS_DIR}")
        raise FileNotFoundError(f"Embeddings directory not found: {EMBEDDINGS_DIR}")
    
    if num_docs is None:
        filename = EMBEDDING_FILES[-1]
        log.info(f"No num_docs specified, using full dataset file: {filename}")
    elif num_docs <= 100000:
        filename = EMBEDDING_FILES[100000]
        log.info(f"num_docs={num_docs} <= 100000, using small file: {filename}")
    elif num_docs <= 1000000:
        filename = EMBEDDING_FILES[1000000]
        log.info(f"num_docs={num_docs} <= 1000000, using 1M file: {filename}")
    else:
        filename = EMBEDDING_FILES[-1]
        log.info(f"num_docs={num_docs} > 1000000, using full file: {filename}")
        
    filepath = os.path.join(EMBEDDINGS_DIR, filename)
    
    if not os.path.exists(filepath):
        log.error(f"Embeddings file not found: {filepath}")
        log.error(f"Directory contents: {os.listdir(EMBEDDINGS_DIR) if os.path.exists(EMBEDDINGS_DIR) else 'N/A'}")
        raise FileNotFoundError(
            f"Embeddings file not found: {filepath}. "
            f"Expected files: {list(EMBEDDING_FILES.values())}"
        )
    
    # Log file size
    file_size = os.path.getsize(filepath)
    log.info(f"Selected file: {filepath} (size: {file_size / 1024 / 1024:.2f} MB)")
        
    return filepath


try:
    from acouchbase.cluster import Cluster, get_event_loop
    from acouchbase.bucket import Bucket
    from acouchbase.collection import Collection
    from couchbase.auth import PasswordAuthenticator
    from couchbase.options import ClusterOptions, ClusterTimeoutOptions, MutateInOptions
    from couchbase.subdocument import upsert
except ImportError as e:
    print(f"Error: couchbase package required. Install with: pip install couchbase\n{e}")
    sys.exit(1)


class CSRReader:
    """
    Reader for custom binary CSR matrix files.
    
    File format:
        Header: 3 x uint64 (rows, cols, non_zeros)
        indptr: (rows+1) x uint64 (row offsets)
        indices: non_zeros x uint32 (column indices)
        data: non_zeros x float32 (values)
    """
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.file = None
        self.num_rows: int = 0
        self.num_cols: int = 0
        self.num_non_zeros: int = 0
        self.indptr: Tuple[int, ...] = ()
        self._indices_offset: int = 0
        self._data_offset: int = 0
        
    def open(self):
        """Open file and read header + indptr."""
        self.file = open(self.file_path, 'rb')
        
        # Read header
        header = struct.unpack('QQQ', self.file.read(24))
        self.num_rows, self.num_cols, self.num_non_zeros = header
        
        # Read indptr
        indptr_size = (self.num_rows + 1) * 8
        self.indptr = struct.unpack(f'{self.num_rows + 1}Q', self.file.read(indptr_size))
        
        # Store offsets for indices and data sections
        self._indices_offset = self.file.tell()
        self._data_offset = self._indices_offset + self.num_non_zeros * 4
        
    def close(self):
        if self.file:
            self.file.close()
            self.file = None
            
    def __enter__(self):
        self.open()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
    
    def get_row(self, row_idx: int) -> List[Any]:
        """
        Get a single row as [[indices], [values]].
        
        Args:
            row_idx: Row index (0-based)
            
        Returns:
            [[indices_list], [values_list]]
        """
        if row_idx < 0 or row_idx >= self.num_rows:
            raise IndexError(f"Row {row_idx} out of range [0, {self.num_rows})")
            
        start = self.indptr[row_idx]
        end = self.indptr[row_idx + 1]
        nnz = end - start
        
        # Seek and read indices
        self.file.seek(self._indices_offset + start * 4)
        indices = struct.unpack(f'{nnz}I', self.file.read(nnz * 4))
        
        # Seek and read values
        self.file.seek(self._data_offset + start * 4)
        values = struct.unpack(f'{nnz}f', self.file.read(nnz * 4))
        
        return [list(indices), list(values)]
    
    def __len__(self) -> int:
        return self.num_rows
    
    def iterate_rows(self, start_offset: int = 0, limit: Optional[int] = None) -> Iterator[List[Any]]:
        """
        Iterate over rows sequentially.
        
        Args:
            start_offset: Starting row index
            limit: Maximum rows to yield (None for all remaining)
            
        Yields:
            [[indices], [values]] for each row
        """
        end_row = self.num_rows if limit is None else min(start_offset + limit, self.num_rows)
        
        for row_idx in range(start_offset, end_row):
            yield self.get_row(row_idx)


class NPZCSRReader:
    """
    Reader for SciPy .npz sparse matrix files.
    """
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.matrix = None
        self.num_rows: int = 0
        self.num_cols: int = 0
        
    def open(self):
        try:
            from scipy import sparse
            import numpy as np
        except ImportError:
            raise ImportError("scipy required for .npz files: pip install scipy numpy")
            
        data = np.load(self.file_path, allow_pickle=True)
        
        # Handle different scipy sparse formats
        if 'format' in data:
            fmt = data['format'].item()
            if fmt == 'csr':
                self.matrix = sparse.csr_matrix(
                    (data['data'], data['indices'], data['indptr']),
                    shape=data['shape']
                )
            else:
                # Convert to CSR
                self.matrix = sparse.csr_matrix(
                    (data['data'], data['indices'], data['indptr']),
                    shape=data['shape']
                )
        else:
            # Assume CSR format
            self.matrix = sparse.csr_matrix(
                (data['data'], data['indices'], data['indptr']),
                shape=tuple(data['shape'])
            )
            
        self.num_rows = self.matrix.shape[0]
        self.num_cols = self.matrix.shape[1]
        
    def close(self):
        if self.matrix is not None:
            self.matrix = None
            
    def __enter__(self):
        self.open()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
    
    def get_row(self, row_idx: int) -> List[Any]:
        """Get row as [[indices], [values]]."""
        row = self.matrix[row_idx]
        indices = row.indices.tolist()
        values = row.data.tolist()
        return [indices, values]
    
    def __len__(self) -> int:
        return self.num_rows
    
    def iterate_rows(self, start_offset: int = 0, limit: Optional[int] = None) -> Iterator[List[Any]]:
        end_row = self.num_rows if limit is None else min(start_offset + limit, self.num_rows)
        for row_idx in range(start_offset, end_row):
            yield self.get_row(row_idx)


def detect_format(file_path: str) -> str:
    """Detect if file is custom CSR or NPZ."""
    _, ext = os.path.splitext(file_path.lower())
    if ext == '.npz':
        return 'npz'
    
    # Try to detect custom CSR by reading header
    with open(file_path, 'rb') as f:
        header = f.read(24)
        if len(header) == 24:
            rows, cols, nnz = struct.unpack('QQQ', header)
            # Sanity check: rows and cols should be reasonable
            if 0 < rows < 10**9 and 0 < cols < 10**9 and 0 <= nnz <= rows * cols:
                return 'csr'
    
    # Default to trying NPZ
    return 'npz'


def get_reader(file_path: str):
    """Get appropriate reader for the file."""
    fmt = detect_format(file_path)
    if fmt == 'npz':
        return NPZCSRReader(file_path)
    else:
        return CSRReader(file_path)


class Metrics:
    """Track and report throughput metrics."""
    
    def __init__(self, progress_interval: float = 5.0):
        self.start_time: float = 0
        self.ops_completed: int = 0
        self.ops_failed: int = 0
        self.last_report_time: float = 0
        self.last_report_ops: int = 0
        self.progress_interval = progress_interval
        
    def start(self):
        self.start_time = time.time()
        self.last_report_time = self.start_time
        
    def increment(self, success: bool = True):
        if success:
            self.ops_completed += 1
        else:
            self.ops_failed += 1
            
    def should_report(self) -> bool:
        now = time.time()
        if now - self.last_report_time >= self.progress_interval:
            self.last_report_time = now
            return True
        return False
    
    def report(self) -> str:
        now = time.time()
        elapsed = now - self.start_time
        interval_ops = self.ops_completed - self.last_report_ops
        interval_time = now - self.last_report_time
        interval_rate = interval_ops / interval_time if interval_time > 0 else 0
        overall_rate = self.ops_completed / elapsed if elapsed > 0 else 0
        
        self.last_report_ops = self.ops_completed
        
        return (f"Progress: {self.ops_completed} ops completed, "
                f"{self.ops_failed} failed, "
                f"current: {interval_rate:.0f} ops/s, "
                f"average: {overall_rate:.0f} ops/s")
    
    def final_report(self) -> str:
        elapsed = time.time() - self.start_time
        rate = self.ops_completed / elapsed if elapsed > 0 else 0
        return (f"\nCompleted: {self.ops_completed} ops in {elapsed:.2f}s "
                f"({rate:.0f} ops/s), {self.ops_failed} failures")


class VectorLoader:
    """
    High-throughput vector embedding loader.
    
    Uses async Couchbase SDK with pipelining and bounded concurrency.
    """
    
    def __init__(self, args):
        self.args = args
        self.cluster: Optional[Cluster] = None
        self.bucket: Optional[Bucket] = None
        self.collection: Optional[Collection] = None
        self.metrics = Metrics(progress_interval=args.progress_every)
        
    async def connect(self):
        """Connect to Couchbase cluster."""
        log.info("Starting connection to Couchbase cluster...")
        log.info(f"Connection string: {self.args.connstr}")
        log.info(f"Username: {self.args.username}")
        log.info(f"TLS enabled: {self.args.tls}")
        
        try:
            auth = PasswordAuthenticator(self.args.username, self.args.password)
            log.info("PasswordAuthenticator created successfully")
        except Exception as e:
            log.error(f"Failed to create authenticator: {e}")
            raise
        
        options = ClusterOptions(
            auth,
            timeout_options=ClusterTimeoutOptions(
                kv_timeout=timedelta(seconds=30.0),
                query_timeout=timedelta(seconds=60.0),
            )
        )
        
        connstr = self.args.connstr
        if self.args.tls:
            # Enable TLS
            options.security = {'trust_store_path': None, 'certpath': None}
            if not connstr.startswith('couchbases://'):
                connstr = connstr.replace('couchbase://', 'couchbases://')
                if not connstr.startswith('couchbases://'):
                    connstr = f'couchbases://{connstr}'
            log.info(f"TLS connection string: {connstr}")
        
        try:
            log.info("Creating and connecting to Cluster...")
            self.cluster = await Cluster.connect(connstr, options)
            log.info("Cluster connected successfully")
        except Exception as e:
            log.error(f"Failed to connect to cluster: {e}")
            log.error(traceback.format_exc())
            raise
        
        try:
            log.info(f"Opening bucket: {self.args.bucket}")
            self.bucket = self.cluster.bucket(self.args.bucket)
            log.info("Bucket reference obtained")
        except Exception as e:
            log.error(f"Failed to open bucket '{self.args.bucket}': {e}")
            log.error(traceback.format_exc())
            raise
        
        try:
            log.info(f"Accessing collection: {self.args.scope}.{self.args.collection}")
            self.collection = self.bucket.scope(self.args.scope).collection(self.args.collection)
            log.info("Collection reference obtained")
        except Exception as e:
            log.error(f"Failed to access collection: {e}")
            log.error(traceback.format_exc())
            raise
        
        log.info("Connection setup complete!")
        
    async def close(self):
        if self.cluster:
            await self.cluster.close()
            
    async def get_document_keys(self) -> List[str]:
        """
        Query document keys in ascending order.
        
        Returns list of document keys sorted by key.
        """
        # If key_prefix is provided (non-empty), generate keys programmatically (much faster)
        if self.args.key_prefix:
            process_count = self.args.limit or 1000000
            if self.args.num_docs:
                process_count = min(process_count, self.args.num_docs)
            
            log.info(f"Generating {process_count} keys with prefix '{self.args.key_prefix}'")
            keys = []
            for i in range(1, process_count + 1):
                # Format: doc00000000000000001 (17 digit number with leading zeros)
                key = f"{self.args.key_prefix}{str(i).zfill(17)}"
                keys.append(key)
            log.info(f"Generated {len(keys)} keys")
            return keys
        
        # Otherwise query from bucket
        query = f"SELECT RAW META().id FROM `{self.args.bucket}`.`{self.args.scope}`.`{self.args.collection}` ORDER BY META().id"
        
        if self.args.limit:
            query += f" LIMIT {self.args.limit + (self.args.start_offset or 0)}"
            
        result = self.cluster.query(query)
        keys = []
        last_log_time = time.time()
        log_interval = 5.0  # Log every 5 seconds
        
        async for row in result:
            keys.append(row)
            # Log progress periodically
            current_time = time.time()
            if current_time - last_log_time >= log_interval:
                log.info(f"Fetched {len(keys)} keys so far...")
                last_log_time = current_time
            
        # Apply start_offset
        if self.args.start_offset:
            keys = keys[self.args.start_offset:]
            
        return keys
    
    async def upsert_embedding(self, key: str, embedding: List[Any], semaphore: asyncio.Semaphore) -> bool:
        """
        Upsert embedding field into document using mutate_in.
        
        Args:
            key: Document key
            embedding: [[indices], [values]]
            semaphore: Concurrency limiter
            
        Returns:
            True if successful
        """
        async with semaphore:
            try:
                # Prepare the embedding value
                value = embedding
                
                # Base64 encode if requested
                if self.args.base64:
                    # Convert to JSON string, then base64 encode
                    json_str = json.dumps(value)
                    value = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
                
                # Determine the path (xattrs don't use $ prefix when xattr=True is set)
                path = 'embedding'
                
                # Create the upsert spec with xattr flag if needed
                spec = upsert(path, value, xattr=self.args.xattrs)
                await self.collection.mutate_in(
                    key,
                    [spec],
                    MutateInOptions(timeout=timedelta(seconds=10.0))
                )
                self.metrics.increment(success=True)
                return True
            except Exception as e:
                self.metrics.increment(success=False)
                error_type = type(e).__name__
                if self.args.verbose:
                    log.error(f"Error upserting key '{key}': {error_type}: {e}")
                    if self.args.verbose > 1:
                        log.error(traceback.format_exc())
                return False
                
    async def run(self):
        """Execute the loading process."""
        log.info("=" * 60)
        log.info("Starting Vector Loader")
        log.info("=" * 60)
        
        # Log configuration
        log.info(f"Configuration:")
        log.info(f"  Connection string: {self.args.connstr}")
        log.info(f"  Bucket: {self.args.bucket}")
        log.info(f"  Scope: {self.args.scope}")
        log.info(f"  Collection: {self.args.collection}")
        log.info(f"  Num docs: {self.args.num_docs}")
        log.info(f"  Concurrency: {self.args.concurrency}")
        log.info(f"  Limit: {self.args.limit}")
        log.info(f"  Start offset: {self.args.start_offset}")
        log.info(f"  TLS: {self.args.tls}")
        log.info(f"  Force: {self.args.force}")
        log.info(f"  Base64: {self.args.base64}")
        log.info(f"  XAttrs: {self.args.xattrs}")
        log.info(f"  Verbose: {self.args.verbose}")
        
        await self.connect()
        
        # Get document keys
        log.info("Querying document keys...")
        try:
            keys = await self.get_document_keys()
            log.info(f"Found {len(keys)} documents")
            if len(keys) > 0:
                log.info(f"First 5 keys: {keys[:5]}")
                log.info(f"Last 5 keys: {keys[-5:]}")
        except Exception as e:
            log.error(f"Failed to query document keys: {e}")
            log.error(traceback.format_exc())
            raise
        
        # Select and open embeddings file
        embeddings_file = select_embeddings_file(self.args.num_docs)
        reader = get_reader(embeddings_file)
        
        with reader:
            log.info(f"Embeddings matrix: {len(reader)} rows x {reader.num_cols} cols")
            log.info(f"Non-zero elements: {reader.num_non_zeros if hasattr(reader, 'num_non_zeros') else 'N/A'}")
            
            # Show sample of first embedding
            if len(reader) > 0:
                sample_embedding = reader.get_row(0)
                log.info(f"Sample embedding (row 0):")
                log.info(f"  Indices count: {len(sample_embedding[0])}")
                log.info(f"  Values count: {len(sample_embedding[1])}")
                if len(sample_embedding[0]) > 0:
                    log.info(f"  First 5 indices: {sample_embedding[0][:5]}")
                    log.info(f"  First 5 values: {sample_embedding[1][:5]}")
            
            # Determine how many rows to process (minimum of keys and embeddings)
            effective_rows = len(reader) - (self.args.start_offset or 0)
            if self.args.limit:
                effective_rows = min(self.args.limit, effective_rows)
            
            # Take minimum of available keys and embeddings
            process_count = min(len(keys), effective_rows)
            
            if len(keys) != effective_rows:
                log.warning(f"Key count ({len(keys)}) != embedding rows ({effective_rows})")
                log.info(f"Will process {process_count} documents (minimum of both)")
            
            # Truncate keys to match process count
            keys = keys[:process_count]
                    
            # Concurrency control
            log.info(f"Starting upsert with concurrency={self.args.concurrency}")
            log.info(f"Processing {len(keys)} documents")
            semaphore = asyncio.Semaphore(self.args.concurrency)
            self.metrics.start()
            
            tasks = []
            processed = 0
            
            # Pair keys with embeddings (limited to process_count)
            row_iter = reader.iterate_rows(
                start_offset=self.args.start_offset or 0,
                limit=process_count
            )
            
            for key, embedding in zip(keys, row_iter):
                task = asyncio.create_task(self.upsert_embedding(key, embedding, semaphore))
                tasks.append(task)
                processed += 1
                
                # Report progress
                if self.metrics.should_report():
                    log.info(self.metrics.report())
                    
                # Limit in-flight tasks
                if len(tasks) >= self.args.concurrency * 2:
                    await asyncio.gather(*tasks[:self.args.concurrency])
                    tasks = tasks[self.args.concurrency:]
                    
            # Wait for remaining tasks
            if tasks:
                log.info(f"Waiting for {len(tasks)} remaining tasks...")
                await asyncio.gather(*tasks)
                
        log.info(self.metrics.final_report())
        log.info("=" * 60)
        log.info("Vector Loader Complete")
        log.info("=" * 60)
        await self.close()


def main():
    parser = argparse.ArgumentParser(
        description='Load vector embeddings into Couchbase documents',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Load 100K embeddings
  %(prog)s --connstr couchbase://localhost --username Administrator --password password \\
           --bucket default --scope _default --collection _default --num-docs 100000

  # Load 1M embeddings with TLS
  %(prog)s --connstr couchbases://cluster.example.com --tls \\
           --username user --password pass --bucket mybucket \\
           --scope myscope --collection mycollection --num-docs 1000000

  # Load full dataset (omit --num-docs)
  %(prog)s --connstr couchbase://localhost --username user --password pass \\
           --bucket mybucket --scope myscope --collection mycollection
"""
    )
    
    # Connection
    parser.add_argument('--connstr', required=True, help='Couchbase connection string')
    parser.add_argument('--username', required=True, help='Username')
    parser.add_argument('--password', required=True, help='Password')
    parser.add_argument('--tls', action='store_true', help='Use TLS')
    
    # Target
    parser.add_argument('--bucket', required=True, help='Bucket name')
    parser.add_argument('--scope', required=True, help='Scope name')
    parser.add_argument('--collection', required=True, help='Collection name')
    
    # Embeddings selection
    parser.add_argument('--num-docs', type=int, default=None,
                        help='Number of documents (100000=100K, 1000000=1M, omit for full)')
    
    # Key generation (skip query if prefix provided)
    parser.add_argument('--key-prefix', type=str, default='doc',
                        help='Key prefix for generating keys (default: doc -> doc00000000000000001). Set to empty string to query bucket instead.')
    
    # Throughput tuning
    parser.add_argument('--concurrency', type=int, default=100,
                        help='Max concurrent operations (default: 100)')
    parser.add_argument('--pipeline-depth', type=int, default=200,
                        help='Pipeline depth for batching (default: 200)')
    
    # Range control
    parser.add_argument('--limit', type=int, help='Maximum documents to process')
    parser.add_argument('--start-offset', type=int, default=0,
                        help='Start offset in embeddings file (default: 0)')
    
    # Progress
    parser.add_argument('--progress-every', type=float, default=5.0,
                        help='Seconds between progress reports (default: 5)')
    
    # Safety
    parser.add_argument('--force', action='store_true',
                        help='Proceed even if key count != embedding rows')
    
    # Embedding format options
    parser.add_argument('--base64', action='store_true',
                        help='Base64 encode the embedding vector')
    parser.add_argument('--xattrs', action='store_true',
                        help='Store embedding in extended attributes (xattrs)')
    
    parser.add_argument('--verbose', '-v', action='count', default=0,
                        help='Verbose output (-v for errors, -vv for debug)')
    
    args = parser.parse_args()
    
    # Set logging level based on verbose
    if args.verbose >= 2:
        logging.getLogger().setLevel(logging.DEBUG)
        log.setLevel(logging.DEBUG)
    elif args.verbose >= 1:
        logging.getLogger().setLevel(logging.DEBUG)
        log.setLevel(logging.INFO)
    
    # Run
    log.info("Initializing vector loader...")
    loop = get_event_loop()
    loader = VectorLoader(args)
    loop.run_until_complete(loader.run())


if __name__ == '__main__':
    main()

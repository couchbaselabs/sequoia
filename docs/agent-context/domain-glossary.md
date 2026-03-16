# Domain Glossary - Sequoia

## Couchbase Services

**Couchbase Server** - NoSQL document database with multiple services:
- **Data Service** - Key-value storage and CRUD operations
- **Index Service (2i/GSI)** - Global secondary indexes using GSI (Global Secondary Index)
- **Query Service (N1QL)** - SQL-like query language for JSON documents
- **Analytics Service (CBAS)** - Couchbase Analytics Service (formerly CBAS)
- **Search Service (FTS)** - Full Text Search with vector search support
- **Eventing Service** - JavaScript functions for real-time document processing
- **Backup/Restore** - cbbackupmgr for incremental backups

**Sync Gateway (SGW)** - Mobile synchronization service that syncs documents between Couchbase Server and mobile apps

**XDCR (Cross Data Center Replication)** - Replicates data between Couchbase clusters across data centers

**CBAS (Couchbase Analytics Service)** - Now called Analytics Service, provides OLAP analytics on operational data

## Framework Terms

**Sequoia** - Docker-based scalable testing framework for Couchbase

**Scope** - Infrastructure definition file (`scope_*.yml`) that defines provisioned resources (servers, buckets, users, clusters)

**Test** - Action definition file (`test_*.yml`) that defines test steps and workloads against the infrastructure

**Template** - Reusable test section (`tests/templates/*.yml`) included in tests to avoid repetition

**Suite** - Collection of tests (`suite.yml`) that run multiple tests with their scopes in sequence

**Provider** - Infrastructure provisioning mechanism:
- **Docker provisioner** - Spins up Couchbase containers dynamically
- **File provisioner** - Connects to pre-existing remote servers
- **Dev provisioner** - Uses local cluster-run
- **Swarm provisioner** - Uses Docker Swarm for distributed containers

**Container Manager** - Manages Docker container lifecycle (create, start, stop, remove)

**Spec** - YAML-defined specifications for infrastructure:
- `ServerSpec` - Couchbase server configuration
- `BucketSpec` - Bucket configuration (RAM, replicas, type)
- `UserSpec` - RBAC users and roles
- `ActionSpec` - Test actions and commands

## Storage Engines

**Couchstore(KV)** - Default storage engine (file-based). 
**Magma(KV)** - New storage engine for better performance (Neo release+)
**Plasma(GSI)** - Alternative storage engine for specific use cases

## Couchbase Code Names

**Mad Hatter** - Couchbase 6.x releases
**Cheshire Cat** - Couchbase 7.0
**Neo** - Couchbase 7.2
**Morpheus** - Couchbase 8.0 (specific features)
**Totoro** - Couchbase 8.1 (RBAC and related features)

## Test Containers

**Testrunner** - Python-based test framework (submodule: github.com/couchbase/testrunner)

**Perfrunner** - Python-based performance testing framework (github.com/couchbaselabs/perfrunner)

**Pillowfight** - KV workload generator based on libcouchbase SDK

**Gideon** - Document mutation tool for testing

**Catapult** - Document load generator

**TPCC** - TPC-C benchmark workload for OLTP testing

**YCSB** - Yahoo! Cloud Serving Benchmark for NoSQL databases

**Vegeta** - HTTP load testing tool

**FleXDR** - Flexible XDCR testing (if present)

## Vector Search and FTS

**Vector Embeddings** - Dense vector representations for semantic search
**KNN (K-Nearest Neighbors)** - Vector similarity search algorithm
**Hierarchical Search** - Multi-level vector search architecture
**FTS Index Manager** - Manages full-text search indexes
**Vector Loader** - Generates and loads vector embeddings for testing

## Test Patterns

**RBAC (Role-Based Access Control)** - Testing user permissions and roles
**DGM (Disk greater than memory)** - Testing data loaded is greater than memory
**Durability** - Testing persistence guarantees (majority, majority+persist, etc.)
**Rebalance** - Testing cluster-scale operations (add/remove nodes)
**Failover** - Testing node failure scenarios (auto/gradual failover)
**Server Groups** - Testing rack awareness and server group failover
**Transactions** - Testing multi-document ACID transactions
**Collections** - Testing scoped buckets with multiple collections
**Encryption** - Testing at-rest encryption features

## Configuration Terms

**Scale** - Multiplier for workload sizes (documents, operations, etc.)
**Repeat** - Number of times to repeat a test
**Skip Setup/Teardown** - Flags to skip initialization or cleanup
**Network** - Docker network mode for container communication

**REST Port** - Couchbase REST API port (default 8091)
**Couchbase Port** - Bucket port (default 11210)
**Query Port** - N1QL service port (default 8093)
**FTS Port** - Search service port (default 8094)
**Analytics Port** - CBAS service port (default 8095)
**Eventing Port** - Eventing service port (default 8096)

## Log and Output

**TAP4J** - Test Anything Protocol XML format used by Sequoia results
**Results Tap** - Generated test output file: `logs/results.tap4j`
**Debug Logs** - Debug output in `logs/` directory
**Host Serializer** - Converts hostnames to IPs for container networking

## Mobile Testing

**Mobile** - Sync Gateway mobile sync testing
**SGW Containers** - Sync Gateway Docker containers
**LB (Load Balancer)** - Load balancer for mobile sync traffic
**SGW Config** - Sync Gateway configuration templates

## Common Acronyms

-DGM - Disk Guardrail/Management
- CBAS - Couchbase Analytics Service
- SDK - Software Development Kit
- KV - Key-Value (Data Service)
- GSI - Global Secondary Index
- DCP - Database Change Protocol (for replication)
- RBAC - Role-Based Access Control
- CI/CD - Continuous Integration/Continuous Deployment
- BUCKETS - Couchbase data containers
- CLUSTERS - Couchbase server nodes
- NODES - Individual Couchbase servers in a cluster
- REPLICA - Data replicas for high availability
- EPHEMERAL - In-memory bucket type
- COUCHBASE - Persistent bucket type
- MOI - Memory-Optimized Indexing
- CDC - Change Data Capture
- KV_OPT - KV optimization features
- HTP - Hybrid Throughput Performance (usually disabled in containers)

## Testing Environment Terms

**Integration** - Full-stack tests across all services
**Steady State** - Long-running stability tests
**Cluster Operations** (Clusterops) - Testing scale-up/down, rebalance, failover
**Volume Testing** - High-scale load testing (10K collections, etc.)
**Component Testing** - Individual service testing
**Longevity Testing** - End-to-end testing across multiple components

## Version-Specific Features

**Free Tier** - Capella free tier testing
**Compression** - Storage compression features
**History Retention** - Document change history for time travel
- Client Certificate Handling - Authentication via certificates
- Encryption at Rest - Data encryption on disk
- Collections/Scopes - Namespaces within buckets
- Durable Writes - Persistence guarantees
## Provider Configuration

**Docker Client** - Docker daemon endpoint (unix socket or TCP)
**Certificate Management** - TLS certificates for HTTPS Docker connections
- SSH Access - Required for file provider remote servers
- VPN - Required for remote cluster access in many environments

## Unknown Terms

**Local/Local Setup** - Referenced but not fully explained (possibly local development)
**FleXDR** - Mentioned in configs but not documented locally
**Spring** - Container exists, purpose unclear (possibly Spring testing)
**Jinja** - Template processing container, usage unclear

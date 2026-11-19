# python:3.9, not 3.7: couchbase 4.2.1 ships prebuilt wheels for 3.8 to 3.11 only, so on 3.7 pip compiled the whole C++ SDK
# from source on every cold build (minutes natively, far longer under amd64 emulation on an Apple Silicon Mac)
# the data image is published for linux/amd64 only: pin it, or COPY --from resolves it for the host platform (arm64 on an
# Apple Silicon Mac) and fails with "no match for platform in manifest"
FROM --platform=linux/amd64 sequoiatools/bigann_gnd:1 AS gnd

FROM --platform=linux/amd64 python:3.9

# Set ARG for platform
ARG TARGETPLATFORM
WORKDIR /

# Layers that never change come first and the files that change most (queries.json, query_manager.py) come last, so a code
# edit rebuilds two small layers instead of re-running apt and pip
ENV TZ=America/Los_Angeles
RUN apt-get update && \
    apt-get install -y --no-install-recommends tzdata && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && \
    echo $TZ > /etc/timezone && \
    rm -rf /var/lib/apt/lists/*

# BigANN queries (bigann_query.bvecs) and the groundtruth files queries.json names (idx_1M .. idx_20M.ivecs) come from a data image
# built once from ftp.irisa.fr (see containers/bigann_gnd): that server gives ~60 KB/s, and downloading the 537 MB archive here
# made every cold build take hours
# query_manager.py reads the groundtruth files from /gnd/, and the YAMLs pass --query_file /bigann_query.bvecs
COPY --from=gnd /gnd/ /gnd/
COPY --from=gnd /gnd/bigann_query.bvecs /bigann_query.bvecs

ADD requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

COPY sift_groundtruth.ivecs /
COPY sift_query.fvecs /
COPY siftsmall_groundtruth.ivecs /
COPY siftsmall_query.fvecs /
COPY gist_query.fvecs /
COPY base_1M.dev.gt /
COPY base_small.dev.gt /
COPY base_full.dev.gt /
COPY queries.dev.csr /
COPY msmarco_qrels.json /
COPY n1ql_udf.js /
COPY queries.json /
COPY query_manager.py /

ENTRYPOINT [ "python3", "/query_manager.py"]

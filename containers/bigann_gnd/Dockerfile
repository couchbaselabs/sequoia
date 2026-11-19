# Data image: the BigANN query vectors and the groundtruth files query_manager reads, extracted once from the archives on
# ftp.irisa.fr. That server is slow (about 60 KB/s measured: the 537 MB bigann_gnd.tar.gz alone is hours), so query_manager's
# Dockerfile does not download it: it copies these files from this image (the groundtruth files to /gnd/, bigann_query.bvecs
# to /).
# Build and push it once, on a host with a fast link to ftp.irisa.fr:
#   docker buildx build --platform linux/amd64 -t sequoiatools/bigann_gnd:1 --push containers/bigann_gnd
# Without a fast link, seed it from an already published query_manager image instead (no download): Dockerfile.seed.
FROM --platform=linux/amd64 python:3.9 AS fetch
WORKDIR /dl
# -c resumes a dropped download, -t retries
RUN wget -nv -c -t 20 ftp://ftp.irisa.fr/local/texmex/corpus/bigann_gnd.tar.gz
# only the groundtruth files queries.json names (idx_1M, 2M, 5M, 10M, 20M), wherever they sit in the archive
RUN mkdir /gnd && \
    tar -xzf bigann_gnd.tar.gz --wildcards --no-anchored 'idx_1M.ivecs' 'idx_2M.ivecs' 'idx_5M.ivecs' 'idx_10M.ivecs' 'idx_20M.ivecs' && \
    find /dl -name 'idx_*M.ivecs' -exec mv {} /gnd/ \; && \
    test "$(ls /gnd | wc -l)" = 5 && ls -l /gnd
RUN wget -nv -c -t 20 ftp://ftp.irisa.fr/local/texmex/corpus/bigann_query.bvecs.gz && \
    gzip -d bigann_query.bvecs.gz && \
    mv bigann_query.bvecs /gnd/

FROM scratch
COPY --from=fetch /gnd/ /gnd/

FROM --platform=linux/amd64 python:3.7

# Set ARG for platform
ARG TARGETPLATFORM
WORKDIR /
RUN wget ftp://ftp.irisa.fr/local/texmex/corpus/bigann_query.bvecs.gz
RUN gzip -dv bigann_query.bvecs.gz
RUN wget ftp://ftp.irisa.fr/local/texmex/corpus/bigann_gnd.tar.gz
RUN tar -xzvf bigann_gnd.tar.gz
ADD requirements.txt /requirements.txt
ENV CMAKE_POLICY_VERSION_MINIMUM=3.5
RUN pip install -r /requirements.txt
COPY queries.json /
COPY sift_groundtruth.ivecs /
COPY sift_query.fvecs /
COPY siftsmall_groundtruth.ivecs /
COPY siftsmall_query.fvecs /
COPY gist_query.fvecs /
COPY gist_groundtruth.ivecs /
COPY query_manager.py /
ENV TZ=America/Los_Angeles

# Install tzdata and set timezone
RUN apt-get update && \
    apt-get install -y tzdata && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && \
    echo $TZ > /etc/timezone
ENTRYPOINT [ "python3", "/query_manager.py"]
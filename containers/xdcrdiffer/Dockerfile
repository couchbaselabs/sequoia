# Builds xdcrDiffer from source so we track the 8.1 (Totoro) line instead of the
# server image's bundled binary. The 8.1 server image isn't on Docker Hub yet, and
# the differ's `main` branch is the post-Morpheus (8.0) dev tip. Pin a tag/branch
# with --build-arg XDCR_DIFFER_REF=<ref>.
#   docker build -t sequoiatools/xdcrdiffer:8.1 containers/xdcrdiffer/
ARG XDCR_DIFFER_REF=main

FROM golang:1.24 AS builder
ARG XDCR_DIFFER_REF
RUN git clone --branch "${XDCR_DIFFER_REF}" --depth 1 \
        https://github.com/couchbase/xdcrDiffer.git /src
WORKDIR /src
# Static binary so it runs on a slim runtime with no shared-lib deps.
RUN CGO_ENABLED=0 go build -o /out/xdcrDiffer . \
    && cp runDiffer.sh /out/runDiffer.sh && chmod +x /out/runDiffer.sh

FROM python:3.12-slim
# runDiffer.sh -y mode parses the config with mikefarah yq v4 (`yq eval`).
COPY --from=mikefarah/yq:4.53.2 /usr/bin/yq /usr/local/bin/yq
# PyYAML: the runner writes the differ YAML config. ca-certificates for any TLS.
RUN pip install --no-cache-dir pyyaml \
    && apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
# Keep the shipped layout so the runner's /opt/couchbase/bin paths hold, and so
# runDiffer.sh finds the binary in its own dir.
COPY --from=builder /out/xdcrDiffer /opt/couchbase/bin/xdcrDiffer
COPY --from=builder /out/runDiffer.sh /opt/couchbase/bin/runDiffer.sh
COPY xdcrdiffer_runner.py /xdcrdiffer_runner.py
ENTRYPOINT ["python3", "/xdcrdiffer_runner.py"]

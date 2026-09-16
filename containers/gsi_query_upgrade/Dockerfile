FROM --platform=linux/amd64 python:3.11-slim

WORKDIR /
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt
COPY index_spec.yml query_suite.yml gsi_query_upgrade.py /

ENTRYPOINT ["python3", "/gsi_query_upgrade.py"]

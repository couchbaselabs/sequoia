FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    git \
    python3 \
    python3-pip \
    python3-dev \
    build-essential \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

COPY cbbackupmerge.py /cbbackupmerge.py

ENTRYPOINT ["python3"]
FROM ubuntu:14.04
RUN apt-get update
RUN apt-get install -y git python-dev python-pip
RUN apt-get install build-essential libssl-dev libffi-dev python-dev
RUN pip install paramiko


COPY cbbackupmerge.py /cbbackupmerge.py
COPY cbbackupcompact.py /cbbackupcompact.py

ENTRYPOINT ["python"]
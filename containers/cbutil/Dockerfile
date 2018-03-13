FROM ubuntu:16.04
RUN apt-key adv --recv-keys --keyserver keyserver.ubuntu.com 16126D3A3E5C1192
RUN apt-get autoclean
RUN apt-get clean all
RUN apt-get clean
RUN rm -rf /var/lib/apt/lists/*
RUN apt-get clean
RUN apt-get update
RUN apt-get upgrade -s
RUN apt-get install -y git python-pip curl tar
RUN apt-get install -y build-essential libssl-dev libffi-dev python-dev


RUN pip install httplib2
RUN pip install paramiko

COPY cbinit.py /cbinit.py

ENTRYPOINT ["python"]
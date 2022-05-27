FROM ubuntu:16.04
RUN apt-get update
RUN apt-get upgrade -s
RUN apt-get install -y git python-pip curl tar
RUN apt-get install -y build-essential libssl-dev libffi-dev python-dev

RUN pip install httplib2 dnspython==1.11.1
COPY analyticsManager.py /analyticsManager.py

ENTRYPOINT ["python","analyticsManager.py"]
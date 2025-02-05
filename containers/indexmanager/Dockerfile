FROM ubuntu:20.04
ENV TZ=US/Pacific
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
RUN apt-get update --allow-insecure-repositories
RUN apt-get install -y --allow-unauthenticated gnupg2
RUN apt-key update
RUN apt-get install -y --allow-unauthenticated git git-all python3-dev python3-pip python3-setuptools cmake build-essential
RUN apt-get install  -y --allow-unauthenticated libssl-dev
RUN python3 -m  pip install requests six future couchbase==3.0.10 httplib2 paramiko dnspython boto3
RUN python3 -m  pip install beautifultable
COPY indexmanager.py /indexmanager.py
COPY n1ql_udf.js /n1ql_udf.js
ENTRYPOINT ["python3","-u", "/indexmanager.py"]

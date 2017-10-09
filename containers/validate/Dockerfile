FROM ubuntu:14.04
RUN apt-get update
RUN apt-get install -y git python-dev python-pip

COPY validate_num_items.py /validate_num_items.py

ENTRYPOINT ["python", "/validate_num_items.py"]
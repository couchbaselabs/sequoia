FROM ubuntu:14.04
RUN apt-get -y update
RUN apt-get install -y git python-pip
RUN apt-get install -y build-essential libssl-dev libffi-dev python-dev
RUN pip install httplib2

COPY eventing.py /eventing.py
COPY bucket_op_function.json /bucket_op_function.json
COPY cron_timer_op.json /cron_timer_op.json
COPY doc_timer_op.json /doc_timer_op.json

ENTRYPOINT ["python"]
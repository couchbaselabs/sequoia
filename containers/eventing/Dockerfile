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

COPY eventing.py /eventing.py
COPY eventing_validator.py /eventing_validator.py
COPY bucket_op_function.json /bucket_op_function.json
COPY cron_timer_op.json /cron_timer_op.json
COPY doc_timer_op.json /doc_timer_op.json
COPY bucket_op_function_without_n1ql.json /bucket_op_function_without_n1ql.json

ENTRYPOINT ["python"]
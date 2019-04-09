FROM ubuntu:16.04
RUN apt-get update
RUN apt-get upgrade -s
RUN apt-get install -y git python-pip curl tar
RUN apt-get install -y build-essential libssl-dev libffi-dev python-dev


RUN pip install httplib2 docker
RUN mkdir alice
COPY eventing.py /eventing.py
COPY eventing_validator.py /eventing_validator.py
COPY bucket_op_function.json /bucket_op_function.json
COPY bucket_op_function1.json /bucket_op_function1.json
COPY bucket_op_function2.json /bucket_op_function2.json
COPY bucket_op_function3.json /bucket_op_function3.json
COPY bucket_op_function4.json /bucket_op_function4.json
COPY bucket_op_function5.json /bucket_op_function5.json
COPY bucket_op_function_with_n1ql.json /bucket_op_function_with_n1ql.json
COPY bucket_op_complex_function.json /bucket_op_complex_function.json
COPY bucket_op_complex_function1.json /bucket_op_complex_function1.json
COPY bucket_op_complex_function_with_n1ql.json /bucket_op_complex_function_with_n1ql.json
COPY doc_timer_op_complex.json /doc_timer_op_complex.json
COPY cron_timer_op.json /cron_timer_op.json
COPY doc_timer_op.json /doc_timer_op.json
COPY bucket_op_complex_function_integration.json /bucket_op_complex_function_integration.json
COPY bucket_op_function_integration.json /bucket_op_function_integration.json
COPY alice/* alice/
COPY mad-hatter/* mad-hatter/

ENTRYPOINT ["python"]
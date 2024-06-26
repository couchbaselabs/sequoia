FROM python:3.7
WORKDIR /
ADD requirements.txt /requirements.txt
RUN pip install -r /requirements.txt
COPY queries.json /
COPY query_manager.py /
ENTRYPOINT [ "python3", "/query_manager.py"]

FROM python:3.7

RUN pip install httplib2
RUN pip install couchbase==3.0.10 dnspython
COPY collectionsUtil.py collectionsUtil.py
ENTRYPOINT ["python","collectionsUtil.py"]
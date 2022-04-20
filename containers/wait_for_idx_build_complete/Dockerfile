FROM ubuntu:18.04
RUN apt-get update
RUN apt-get install -y git python-dev python-pip -f
RUN pip install requests dnspython

COPY wait_for_idx_build_complete.py /wait_for_idx_build_complete.py

ENTRYPOINT ["python", "/wait_for_idx_build_complete.py"]
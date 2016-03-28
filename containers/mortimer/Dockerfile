FROM ubuntu_python
COPY mortimer.tar .
RUN  tar -xf mortimer.tar
WORKDIR mortimer
RUN pip install tornado requests
RUN apt-get -y install sshpass
COPY wait_for_collection.py .
COPY publish.sh .

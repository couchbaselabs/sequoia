FROM ubuntu:20.04
ENV TZ=US/Pacific
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
RUN apt-get update
RUN apt-get install -y git git-all python3-dev python3-pip python3-setuptools cmake build-essential curl unzip
RUN apt-get install libssl-dev
RUN python3 -m  pip install requests dnspython

COPY loganalysis.py /loganalysis.py
COPY analyze.sh /analyze.sh
RUN chmod 777 /analyze.sh

ENTRYPOINT ["python3","/loganalysis.py"]
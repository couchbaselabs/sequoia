FROM ubuntu:14.04
RUN apt-get update
RUN apt-get install -y curl maven openjdk-7-jre
RUN curl -O --location https://github.com/brianfrankcooper/YCSB/releases/download/0.12.0/ycsb-0.12.0.tar.gz
RUN tar xfvz ycsb-0.12.0.tar.gz
WORKDIR ycsb-0.12.0
ENTRYPOINT ["bin/ycsb.sh"]

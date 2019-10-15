FROM ubuntu:16.04
RUN apt-get update
RUN apt-get install -y curl maven atop cpufrequtils git golang-go htop libcurl4-gnutls-dev libffi-dev libsnappy-dev libssl-dev linux-tools-generic nvi openjdk-8-jdk python-pip python-virtualenv python3-dev sshpass rpm2cpio memcached
RUN git clone -b soe https://github.com/girishmind/YCSB.git
WORKDIR YCSB

COPY ./memcached.conf /etc/memcached.conf
EXPOSE 8000
RUN update-rc.d memcached enable

COPY ./workloadsmix3 workloads/soe/workloadsmix3
COPY ./run_ycsb.sh /YCSB

ENTRYPOINT ["/YCSB/run_ycsb.sh"]

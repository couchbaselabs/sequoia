FROM centos:7
RUN yum update -y
RUN yum install git wget python3 iproute -y
RUN yum install gcc libffi-devel python3-devel python3-pip openssl-devel -y

RUN wget http://packages.couchbase.com/releases/couchbase-release/couchbase-release-1.0-8-x86_64.rpm
RUN rpm -iv couchbase-release-1.0-8-x86_64.rpm
RUN yum install libcouchbase-devel libcouchbase2-bin gcc-c++ -y

RUN pip3 install virtualenv
RUN ssh-keygen -q -t rsa -N '' -f ~/.ssh/id_rsa <<<y 2>&1 >/dev/null

RUN git clone git://github.com/couchbaselabs/mobile-testkit
WORKDIR mobile-testkit

COPY sgw_command.sh sgw_command.sh

ENTRYPOINT ["./sgw_command.sh"]

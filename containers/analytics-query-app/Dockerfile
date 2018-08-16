FROM centos:7
MAINTAINER vikas chaudhary <vikas.chaudhary@couchbase.com>

# install base packages
RUN yum update -y
RUN yum install -y java-1.8.0-openjdk-devel git wget openssl-devel
ENV JAVA_HOME=/usr/lib/jvm/java
ENV JYTHON_VERSION 2.7.0

RUN curl -L "http://search.maven.org/remotecontent?filepath=org/python/jython-installer/${JYTHON_VERSION}/jython-installer-${JYTHON_VERSION}.jar" -o jython_installer-${JYTHON_VERSION}.jar && \
    java -jar jython_installer-${JYTHON_VERSION}.jar -s -d /jython-${JYTHON_VERSION} -i ensurepip && \
    ln -s /jython-${JYTHON_VERSION}/bin/jython /usr/bin && \
    ln -s /jython-${JYTHON_VERSION}/bin/pip /usr/bin && \
    rm jython_installer-${JYTHON_VERSION}.jar

RUN git clone https://github.com/couchbaselabs/AnalyticsQueryApp.git

WORKDIR /AnalyticsQueryApp/Query
RUN git pull
RUN chmod 777 load_queries.py
ENTRYPOINT ["jython"]
FROM ubuntu:trusty

MAINTAINER Milos Prchlik <happz@happz.cz>

ENV VIRTUAL_ENV=/usr/local

RUN mkdir -p /usr/local/bin
COPY build.sh /usr/local/bin/build.sh

RUN apt-get update && apt-get install -y build-essential lsb-release gcc git make ninja-build python-dev scons wget
RUN wget https://bootstrap.pypa.io/get-pip.py && python get-pip.py && rm -f get-pip.py
RUN pip install colorama six

ENTRYPOINT ["/usr/local/bin/build.sh"]

#!/bin/bash
set -e
echo Install required packages
yum update -y
yum install -y gcc make cmake
yum install -y gcc-c++.x86_64
yum install -y libev libevent libev-devel libevent-devel
echo Successfully installed required packages

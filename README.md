# sequoia
Scalable couchbase testing with docker

**Install Docker**
* Mac - https://docs.docker.com/mac/
* Ubuntu - https://docs.docker.com/engine/installation/linux/ubuntulinux/

**Install Go**
* Ubuntu - https://github.com/golang/go/wiki/Ubuntu
* CentOS - http://itekblog.com/centos-golang/
* Any - https://golang.org/dl/ 
 

**Run Tests**
```bash
go get github.com/couchbaselabs/sequoia
go build
./sequoia  

# see config.yml or specify via cli
./sequoia -scope tests/longevity/scope_8x4.yml -test tests/longevity/test_allFeatures.yml 
```

# sequoia
Scalable couchbase testing with docker

**Install Docker**
* Mac - https://docs.docker.com/mac/
* Ubuntu - https://docs.docker.com/engine/installation/linux/ubuntulinux/

**Install Go**
* Ubuntu - https://github.com/golang/go/wiki/Ubuntu
* CentOS - http://itekblog.com/centos-golang/
* Any - https://golang.org/dl/ 
 
**Build Containers**
```bash
./build.sh
```

**Run Simple Test**
```bash
go get github.com/couchbaselabs/sequoia
go build
./sequoia config.yml
```

# sequoia
Scalable couchbase testing with docker

**Install Docker**
* Mac - https://docs.docker.com/mac/
* Ubuntu - https://docs.docker.com/engine/installation/linux/ubuntulinux/

**Requires Go**
* Download - https://golang.org/dl/ 


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

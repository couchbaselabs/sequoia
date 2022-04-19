# sequoia
Scalable testing with docker

**Install Docker**
* Mac - https://docs.docker.com/mac/
* Ubuntu - https://docs.docker.com/engine/installation/linux/ubuntulinux/
* CentOS - https://docs.docker.com/engine/installation/linux/centos/

**Install Go (1.7+)**
* Ubuntu - https://github.com/golang/go/wiki/Ubuntu
* CentOS - http://itekblog.com/centos-golang/
* Any - https://golang.org/dl/ 
 
**Build**
```bash
cd $GOPATH/src/github.com/couchbaselabs/
git clone https://github.com/couchbaselabs/sequoia.git
cd sequoia
go mod init
go mod tidy
go build -o sequoia
```

## Getting Started

From the command-line:  

```bash
# run simple test
./sequoia

# override the default test and scope
./sequoia -scope tests/simple/scope_medium.yml -test tests/simple/test_views.yml

```

### Running with a docker network (EXPERIMENTAL)
```
./sequoia -scope tests/simple/scope_medium.yml -test tests/simple/test_views.yml --network cbl
```

Refer to [Test Syntax](https://github.com/couchbaselabs/sequoia/wiki/Test-Syntax) for more information about how to build out your test and scopes.

## Client

Sequoia works by running containers that apply load to couchbase servers.  These containers are running on docker specified by the client in your config file.  Depending on your docker install you will need to use http(s) and specify port.  It's recommended to run over a tcp port.  

```yaml
# config.yml
...
client:  https://192.168.99.100:2376
```

Or on server without https and daemon running on port 2375

```yams
# config.yml
...
client:  http://172.23.97.124:2375
```


## Providers

Providers help decouple test and provisioning from the mechanisms that provide couchbase resources so that the same scope can present an identical environment to different tests.  You can change your provider via the config file.

```yaml
# config.yml
...
provider: docker  # dev, file
```

Read More about [Providers Here](https://github.com/couchbaselabs/sequoia/wiki/Providers)






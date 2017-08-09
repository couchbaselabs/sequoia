### Testrunner workflow
Sequoia can be used to quickly spin up a clean set of containers for use with testrunner.  

Prior to running this be sure to check out the testrunner submodule: 
```bash
git submodule update --init --recursive
```

Now we can quickly run any test by passing the 'testrunner' arg to sequoia:
```bash
./sequoia testrunner -command \
    "-i b/resources/4-nodes-template.ini -c conf/simple.conf"
```
You can run this command as many times as you want and each time new containers will start.

### Saving results
Results can be copied from container via 'docker cp' command.  The key is to specify a container name when starting the test
```bash
# container name is 'my_test'
./sequoia testrunner -command  "-i b/resources/1-node-template.ini -c conf/py-epeng-basic-ops.conf"\
                      -container_name my_test

# copy results
docker cp my_testv:/testrunner/logs .
```

### Specifying builds, platforms, etc... 
By default couchbase containers are built according to params inside of 'providers/docker/options.yml'.  These options can be overriden via the -override flag.
```bash
# specify spock build 5.0.0-3217
./sequoia testrunner -command "-i b/resources/1-node-template.ini -c conf/py-epeng-basic-ops.conf"\
                      -override docker:build=5.0.0-3217

# build containers with 8gb memory
./sequoia testrunner -command "-i b/resources/1-node-template.ini -c conf/py-epeng-basic-ops.conf"\
                      -override docker:memory=8000000000

# run against a toy build
./sequoia testrunner -command "-i b/resources/1-node-template.ini -c conf/py-epeng-basic-ops.conf"\
                      -override docker:url=http://172.23.120.24/builds/latestbuilds/couchbase-server/spock/4638/couchbase-server-enterprise-5.0.1-4638-centos7.x86_64.rpm

# Arguments can be combined by separating with a comma
# ie. build 5.0.0-3217 on centos7 with 8gb memory
./sequoia testrunner -command "-i b/resources/1-node-template.ini -c conf/py-epeng-basic-ops.conf"\
                      -override docker:build=5.0.0-3217,docker:memory=8000000000,docker=os:centos7

```
### Debugging Testrunner
If instead you wanted to manually run a testrunner test, simply provide the --exec option and you will have a debeugging environment to run your tests:
```bash
./sequoia testrunner \
   -command "-i b/resources/4-nodes-template.ini -c conf/simple.conf" \
   --exec
```

### Build new image
To build a new testrunner image, run in exec mode, then do a commit + tag + push
```bash
docker build -t sequoiatools/testrunner containers/testrunner
```

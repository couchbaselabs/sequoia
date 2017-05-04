#Example commands to run situational tests

## Build libcouchbase, sdkd-lcb, sdkdclient and run situational tests
set situational test container name <br>
```
export CONTAINER_NAME=situational
```
build situational test with lcb (libcouchbase)
```
cd containers/sdk && ./build.sh lcb 2.7.5 master for_docker)
```
run situational test
```
sequoia sdk --skip_pull -command "-I spock-basic.ini --install-skip true --rebound 90 --testsuite-test=Rb1Swap --testsuite-variants=HYBRID -d all:debug -A S3Creds_tmp -C share/rexec --rexec_path=/root/lcb/sdkd-cpp/sdkd_lcb --rexec_port=8050 --rexec_arg=-l 8050 --rexec_arg=-L log.txt" -container_name ${CONTAINER_NAME}
```

## Build java client, sdkd-java, sdkdclient and run situational tests
set situational test container name
```
export CONTAINER_NAME=situational
```
build situational tests with java SDK
```
cd containers/sdk && ./build.sh java 2.4.5 master for_docker 1.4.5
```
run situational test
```
sequoia sdk --skip_pull -command "-I spock-basic.ini --install-skip true --bucket-password="password" --testsuite-test=Rb1Swap --testsuite-variants=HYBRID -d all:debug -A S3Creds_tmp -C share/rexec --rexec_path=/root/java/sdkd-java/run-sdkd-java --rexec_port=8050" -container_name ${CONTAINER_NAME}
```

# Build java client, sdkd-java, sdkdclient and run situational test as work loader
set situational test container name
```
export CONTAINER_NAME=situational
```
build situational tests with java SDK
```
cd containers/sdk && ./build.sh java 2.4.5 master for_docker 1.4.5
```
run situational test as longevity work loader (this does not change topology but continues workload)
```
sequoia sdk --skip_pull -command "-I spock-basic.ini --install-skip true --bucket-password="password" --testsuite-test=passthrough --wait 86400 --testsuite-variants=HYBRID -d all:debug -A S3Creds_tmp -C share/rexec --rexec_path=/root/java/sdkd-java/run-sdkd-java --rexec_port=8050" -container_name ${CONTAINER_NAME}
```
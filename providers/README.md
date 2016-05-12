## Providers

Sequoia decouples test and provisioning from the mechanisms that provide couchbase resources.  This allows the same scope to present an identical environment to the test regardless of how servers are actually being created.  Every provider used within sequoia implements the following interface:

```go
type Provider interface {
	ProvideCouchbaseServers(servers []ServerSpec)
	GetHostAddress(name string) string
	GetType() string
	GetRestUrl(name string) string
}
```
[Implementation](https://github.com/couchbaselabs/sequoia/blob/master/lib/provider.go)

## Docker Provider

```yaml
# config.yml
provider: docker
```

This is default provider which uses the same docker daemon as the test infrastructure.  Edit the [Docker Provider Options](https://github.com/couchbaselabs/sequoia/blob/master/providers/docker/options.yml) to specify which build will be provided to the scope.  To use docker provider make sure *docker* is set as provider in config.yml


## File Provider

```yaml
# config.yml
provider: file  # reads IP's from providers/file/hosts.yml
```

This is the simplest provider but also the least flexible.  Host IP's are hard coded into the [file providers host file](https://github.com/couchbaselabs/sequoia/blob/master/providers/file/hosts.yml).  File provider is a good option if you have external installers such as ansible or couchbases's install.py.  During setup and test the scope will pull from the provider file in a top-down fashion.  Be sure that your scope does not have more nodes than the provider or behavior is undefined.  To use file provider specify *file* as docker provider in config.yml. 


## Dev provider

```yaml
# config.yml
provider: dev:10.0.0.6
```

For use with cluster_run. Where 10.0.0.6 here would be the public IP of the machine running cluster_run.  This is needed because the docker clients cannot reference 127.0.0.1 since that is localhost of the container itself.  Cluster run needs to be started with # of nodes needed for tests before running. 


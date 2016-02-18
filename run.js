var Docker = require('dockerode')
    , async = require('async')
	, fs = require('fs')
	, assert = require('assert')
    , waitForPort = require('wait-for-port');


var DOCEKRIP = '192.168.99.101'
var SERVERS = {ips: []}

var docker = new Docker({
	protocol: 'https',
	host: DOCEKRIP, 
	port: 2376,
	ca: fs.readFileSync(process.env.DOCKER_CERT_PATH + '/ca.pem'),
	cert: fs.readFileSync(process.env.DOCKER_CERT_PATH + '/cert.pem'),
	key: fs.readFileSync(process.env.DOCKER_CERT_PATH + '/key.pem')
});


/*
describe("Cleanup", function(){
    var _glb = {containers: []} 

    before(function(done) {
        docker.listContainers(function(err, containers){
            _glb.containers = containers
            done()
        })
    });

    it('should stop all containers', function (done) {
        async.each(_glb.containers, function(item, cb){ docker.getContainer(item.Id).stop(cb) }, done)
    })
    it('should remove all containers', function (done) {
        async.each(_glb.containers, function(item, cb){ docker.getContainer(item.Id).remove(cb) }, done)
    })
})

describe("Start Cluster", function(){
    this.timeout(600000)

    var servers = []
    for(var i=1;i<=8;i++){
        servers.push("db"+i)
    }

    servers.forEach(function(name, i){
        it('should start node '+name, function(done) {
            docker.createContainer({Image: 'couchbase-watson', name: name}, function(err, container){
                if(err){done(err)}
                var startOps = {}
                if(i==1){
                    startOps = {"PortBindings": {"8091/tcp": [{"HostPort": "8091"}]}}
                }
                container.start(startOps, done)
            })
        })
    })

    it('did start cluster', function(done){
        waitForPort(DOCEKRIP, 8091, {numRetries:60}, done)
    })

})


*/

describe("Provision Cluster", function(){
    var _glb = {hosts: []} 
    this.timeout(60000) // 1 min

    before(function(done) {
        docker.listContainers(function(err, containers){
            async.each(containers, function(item, cb){ docker.getContainer(item.Id).inspect(function(e,d){
                if(d.Config.Image == "couchbase-watson"){
                    _glb.hosts.push(d.NetworkSettings.IPAddress)
                }
                cb(e)
            }) }, done)
        })
    })
    
    it('init nodes', function(done){
        async.each(_glb.hosts, function(ip, cb){
            docker.run('couchbase-cli', 
                       ['./couchbase-cli', 'node-init', '-c', ip, '-u', 'Administrator', '-p', 'password'], 
                       [process.stdout], 
                       {Tty:false}, cb)
        }, done)
    })

    it('init cluster', function(done){
        docker.run('couchbase-cli', 
           ['./couchbase-cli', 'cluster-init', '-c', _glb.hosts[0], '-u', 'Administrator', '-p', 'password', '--cluster-username', 'Administrator', '--cluster-password', 'password', '--cluster-port', '8091', '--cluster-ramsize', '300', '--services', 'data'], 
           [process.stdout], 
           {Tty:false}, done)
    })
    it('add nodes', function(done){
     var orchestrator = _glb.hosts[0]
     //TODO - USE SPEC!
     async.each(_glb.hosts.splice(1, 3), function(ip, cb){
            docker.run('couchbase-cli', 
                       ['./couchbase-cli', 'server-add', '-c', orchestrator, '-u', 'Administrator', '-p', 'password', '--server-add', ip, '--server-add-username', 'Administrator', '--server-add-password', 'password'], 
                       [process.stdout], 
                       {Tty:false}, cb)
            }, done)
    })

    it('rebalance cluster', function(done){
        var orchestrator = _glb.hosts[0]
        docker.run('couchbase-cli', 
               ['./couchbase-cli', 'rebalance', '-c', orchestrator, '-u', 'Administrator', '-p', 'password'], 
               [process.stdout], 
               {Tty:false}, done)
    })

    it('create bucket', function(done){
        var orchestrator = _glb.hosts[0]
        docker.run('couchbase-cli', 
           ['./couchbase-cli', 'bucket-create', '-c', orchestrator, '-u', 'Administrator', '-p', 'password', '--bucket', 'bucket-1', '--bucket-ramsize', '300', '--bucket-type', 'couchbase', '--wait'], 
           [process.stdout, process.stderr], 
           {Tty:false}, done)    
    })
})


/*
describe("Phase 1 - Start data loading", function(){
    it('should start perfrunner ', function (done) {
        docker.createContainer({Image: 'perfrunner-n1ql', name: 'perf', Links:['db1:db1', 'db2:db2', 'db3:db3', 'db4:db4']}, function(err, container){
            if(err){done(err)}
            container.start(done)
        })
    })

    it('should start gideon kv clients', function(done){
        docker.createContainer({Image: 'gideon', Links:['db1:db1']}, function(err, container){
            if(err){done(err)}
            container.start(done)
        })
    })
})*/


describe("Phase 2: Start XDCR", function(){
    var _glb = {hosts: []} 
    this.timeout(60000) // 1 min

    before(function(done) {
        docker.listContainers(function(err, containers){
            async.each(containers, function(item, cb){ docker.getContainer(item.Id).inspect(function(e,d){
                if(d.Config.Image == "couchbase-watson"){
                    _glb.hosts.push(d.NetworkSettings.IPAddress)
                }
                cb(e)
            }) }, done)
        })
    })

    it('should setup remote replication', function(done){
        var orchestrator = _glb.hosts[0]
        remote_host = _glb.hosts[_glb.hosts.length-1]
        docker.run('couchbase-cli', 
                   ['./couchbase-cli', 'xdcr-setup', '-c', orchestrator, '--create', '--xdcr-cluster-name', 'remote', '--xdcr-hostname', remote_host, '--xdcr-username', 'Administrator', '--xdcr-password', 'password'], 
                   [process.stdout,  process.stderr], 
                   {Tty:false}, done)
    })

    it('should start replication', function(done){
        var orchestrator = _glb.hosts[0]
        docker.run('couchbase-cli', 
                   ['./couchbase-cli', 'xdcr-replicate', '-c', orchestrator, '--xdcr-cluster-name', 'remote', '--xdcr-from-bucket', 'bucket-1', '--xdcr-to-bucket', 'bucket-1'], 
                   [process.stdout,  process.stderr], 
                   {Tty:false}, done)
    })

})

/*
describe("Phase 3 - Remote Rebalance in", function(){
    var _glb = {hosts: []} 
    this.timeout(60000) // 1 min

    before(function(done) {
        docker.listContainers(function(err, containers){
            async.each(containers, function(item, cb){ docker.getContainer(item.Id).inspect(function(e,d){
                if(d.Config.Image == "couchbase-watson"){
                    _glb.hosts.push(d.NetworkSettings.IPAddress)
                }
                cb(e)
            }) }, done)
        })
    })
    it('add nodes', function(done){
     var orchestrator = _glb.hosts[4]
     //TODO - USE SPEC!
     async.each(_glb.hosts.splice(4, 3), function(ip, cb){
            docker.run('couchbase-cli', 
                       ['./couchbase-cli', 'server-add', '-c', orchestrator, '-u', 'Administrator', '-p', 'password', '--server-add', ip, '--server-add-username', 'Administrator', '--server-add-password', 'password'], 
                       [process.stdout], 
                       {Tty:false}, cb)
            }, done)
    })

    it('rebalance cluster', function(done){
        var orchestrator = _glb.hosts[0]
        docker.run('couchbase-cli', 
               ['./couchbase-cli', 'rebalance', '-c', orchestrator, '-u', 'Administrator', '-p', 'password'], 
               [process.stdout], 
               {Tty:false}, done)
    })
})
*/


/*
---
# start single direction xdcr
- hosts: orchestrator
  vars:
    rest_user: "Administrator"
    rest_pass: "password"
    bucket_to: "default"
    bucket_from: "default"
    cluster_name: "remote"
    cli_bin:  "/opt/couchbase/bin/couchbase-cli"
    internal_ip: "{{hostvars[inventory_hostname]['internal']}}"
  remote_user: root
  tasks:
   - name: xdcr setup
     shell: "{{cli_bin}} xdcr-setup -c {{internal_ip}} --create --xdcr-cluster-name={{cluster_name}} --xdcr-hostname={{groups['remote'][0]}}  --xdcr-username={{rest_user}} --xdcr-password={{rest_pass}} -u {{rest_user}} -p {{rest_pass}}"
   - name: xdcr replicate
     shell: "{{cli_bin}} xdcr-replicate -c {{internal_ip}} --xdcr-cluster-name={{cluster_name}}  --xdcr-from-bucket={{bucket_from}} --xdcr-to-bucket={{bucket_to}} -u {{rest_user}} -p {{rest_pass}}"



// loading


# rebalance in 1 node
- hosts: couchbaseservers
  vars:
   data_path: "/data"
   index_path: "/data"
   rest_user: "Administrator"
   rest_pass: "password"
   rest_port: 8091
   cli_bin:  "/opt/couchbase/bin/couchbase-cli"
   internal_ip: "{{hostvars[inventory_hostname]['internal']}}"
  remote_user: root
  tasks:
    - name: join cluster
      shell: "{{cli_bin}} server-add -c {{groups['orchestrator'][0]}}:{{rest_port}} --server-add={{internal_ip}}:{{rest_port}} --server-add-username={{rest_user}} --server-add-password={{rest_pass}} -u {{rest_user}} -p {{rest_pass}}"
      when: hostvars[inventory_hostname]['phase'] == 'primary'


- hosts: orchestrator
  vars:
    rest_user: "Administrator"
    rest_pass: "password"
    cli_bin:  "/opt/couchbase/bin/couchbase-cli"
    internal_ip: "{{hostvars[inventory_hostname]['internal']}}"
  remote_user: root
  tasks:
   - name: rebalance in nodes
     shell: "{{cli_bin}} rebalance -c {{internal_ip}} -u {{rest_user}} -p {{rest_pass}}"



# view queries

*/


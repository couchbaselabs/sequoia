var Docker = require('dockerode')
    , async = require('async')
    , fs = require('fs')
    , assert = require('assert');



var logStream

var DOCKER_HOST = '172.23.121.59'
var docker = new Docker({host: DOCKER_HOST, port: 2375})



describe("Cleanup App Containers", function(){
    this.timeout(60000)
    var _glb = {containers: []}

    before(function(done) {
        docker.listContainers({all:true}, function(err, containers){
            _glb.containers = containers
            done()
        })
    });

    it('should stop running containers', function (done) {
        async.each(_glb.containers, function(item, cb){
          docker.getContainer(item.Id).stop(function(err){
            // ignore stop err
            cb()
          })
        }, done)
    })
    it('should remove all containers', function (done) {
        async.each(_glb.containers, function(item, cb){
            docker.getContainer(item.Id).remove(cb)
        }, done)
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
                i++
                var startOps = {"PortBindings": {"8091/tcp": [{"HostPort": "809"+i}]}}
                container.start(startOps, done)
            })
        })
    })

    servers.forEach(function(name, i){
        it('did start cluster', function(done){
            i++
            var dbLink = "db"+i+":db"+i
            docker.run('martin/wait',
                       ["-p", "8091"],
                       null,
                       {Links:[dbLink]}, done)
        })
    })

})

describe("Provision Cluster", function(){
    var _glb = {hosts: []}
    this.timeout(60000) // 1 min

    before(function(done) {
        docker.listContainers(function(err, containers){
            async.each(containers, function(item, cb){ docker.getContainer(item.Id).inspect(function(e,d){
                if(d.Config.Image == "couchbase-watson"){
                    _glb.hosts.push(d.NetworkSettings.IPAddress)
                    _glb.hosts.sort()
                }
                cb(e)
            }) }, done)
        })
    })

    beforeEach(function(){
	logStream = fs.createWriteStream('log.txt', {flags: 'a'});
     })

    it('init nodes', function(done){
        async.each(_glb.hosts, function(ip, cb){
            docker.run('couchbase-cli',
                       ['./couchbase-cli', 'node-init', '-c', ip, '-u', 'Administrator', '-p', 'password'],
                       [logStream, process.stderr],
                       {Tty:false}, cb)
        }, done)
    })



    it('init cluster', function(done){
        docker.run('couchbase-cli',
           ['./couchbase-cli', 'cluster-init', '-c', _glb.hosts[0], '-u', 'Administrator', '-p', 'password', '--cluster-username', 'Administrator', '--cluster-password', 'password', '--cluster-port', '8091', '--cluster-ramsize', '876', '--services', 'data'],
           [logStream, process.stderr],
           {Tty:false}, done)
    })

    it('add nodes', function(done){
     var orchestrator = _glb.hosts[0]
     //TODO - USE SPEC!
     async.each(_glb.hosts.splice(1, 3), function(ip, cb){
            docker.run('couchbase-cli',
                       ['./couchbase-cli', 'server-add', '-c', orchestrator, '-u', 'Administrator', '-p', 'password', '--server-add', ip, '--server-add-username', 'Administrator', '--server-add-password', 'password'],
                       [process.stdout, process.stderr],
                       {Tty:false}, cb)
            }, done)
    })

    it('rebalance cluster', function(done){
        var orchestrator = _glb.hosts[0]
        docker.run('couchbase-cli',
               ['./couchbase-cli', 'rebalance', '-c', orchestrator, '-u', 'Administrator', '-p', 'password'],
               [logStream, process.stderr],
               {Tty:false}, done)
    })

    it('create bucket', function(done){
        var orchestrator = _glb.hosts[0]
        docker.run('couchbase-cli',
           ['./couchbase-cli', 'bucket-create', '-c', orchestrator, '-u', 'Administrator', '-p', 'password', '--bucket', 'bucket-1', '--bucket-ramsize', '512', '--bucket-type', 'couchbase', '--wait'],
           [logStream, process.stderr],
           {Tty:false}, done)
    })

})

describe("Phase 1: Start data loading", function(){
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
})

describe("Phase 2: Provision Remote Cluster", function(){
    var _glb = {hosts: []}
    this.timeout(60000) // 1 min

    before(function(done) {
        docker.listContainers(function(err, containers){
            async.each(containers, function(item, cb){ docker.getContainer(item.Id).inspect(function(e,d){
                if(d.Config.Image == "couchbase-watson"){
                    _glb.hosts.push(d.NetworkSettings.IPAddress)
                    _glb.hosts.sort()
                }
                cb(e)
            }) }, done)
        })
    })

    beforeEach(function(){
	logStream = fs.createWriteStream('log.txt', {flags: 'a'});
     })

    it('should init remote cluster', function(done){
        var remote_host = _glb.hosts[_glb.hosts.length-1]
        docker.run('couchbase-cli',
           ['./couchbase-cli', 'cluster-init', '-c', remote_host, '-u', 'Administrator', '-p', 'password', '--cluster-username', 'Administrator', '--cluster-password', 'password', '--cluster-port', '8091', '--cluster-ramsize', '300', '--services', 'data'],
           [logStream],
           {Tty:false}, done)
    })

    it('add nodes to remote cluster', function(done){
     var orchestrator = _glb.hosts[_glb.hosts.length-1]
     async.each(_glb.hosts.splice(4, 3), function(ip, cb){
            docker.run('couchbase-cli',
                       ['./couchbase-cli', 'server-add', '-c', orchestrator, '-u', 'Administrator', '-p', 'password', '--server-add', ip, '--server-add-username', 'Administrator', '--server-add-password', 'password'],
                       [process.stdout],
                       {Tty:false}, cb)
            }, done)
    })

    it('rebalance remote cluster', function(done){
        var orchestrator = _glb.hosts[_glb.hosts.length-1]
        docker.run('couchbase-cli',
               ['./couchbase-cli', 'rebalance', '-c', orchestrator, '-u', 'Administrator', '-p', 'password'],
               [logStream],
               {Tty:false}, done)
    })

    it('create remote bucket', function(done){
        var remote_host = _glb.hosts[_glb.hosts.length-1]
        docker.run('couchbase-cli',
           ['./couchbase-cli', 'bucket-create', '-c', remote_host, '-u', 'Administrator', '-p', 'password', '--bucket', 'bucket-1', '--bucket-ramsize', '300', '--bucket-type', 'couchbase', '--wait'],
           [logStream, process.stderr],
           {Tty:false}, done)
    })

    it('should setup remote replication', function(done){
        var orchestrator = _glb.hosts[0]
        var remote_host = _glb.hosts[_glb.hosts.length-1]
        docker.run('couchbase-cli',
                   ['./couchbase-cli', 'xdcr-setup', '-c', orchestrator, '--create', '--xdcr-cluster-name', 'remote', '--xdcr-hostname', remote_host, '--xdcr-username', 'Administrator', '--xdcr-password', 'password'],
                   [logStream,  process.stderr],
                   {Tty:false}, done)
    })

    it('should start replication', function(done){
        var orchestrator = _glb.hosts[0]
        docker.run('couchbase-cli',
                   ['./couchbase-cli', 'xdcr-replicate', '-c', orchestrator, '--xdcr-cluster-name', 'remote', '--xdcr-from-bucket', 'bucket-1', '--xdcr-to-bucket', 'bucket-1'],
                   [logStream,  process.stderr],
                   {Tty:false}, done)
    })

})


describe("Phase 3: start view queries", function(){
    this.timeout(0)
    beforeEach(function(){
	logStream = fs.createWriteStream('log.txt', {flags: 'a'});
     })
    it('should start run view query container ', function (done) {
        docker.run('perfrunner-n1ql',
                   ['/tmp/env/bin/python', '-m', 'perfrunner', '-c', 'clusters/systest.spec', '-t', 'tests/query_dev_20M_group_by.test', '--local'],
                   [logStream,  process.stderr],
                   {Tty:false, Links:['db1:db1', 'db2:db2', 'db3:db3', 'db4:db4']}, done)
    })
})

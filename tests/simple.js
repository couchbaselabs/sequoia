var Docker = require('dockerode')
    , async = require('async')
    , fs = require('fs')
    , assert = require('assert');


var logStream

var DOCKER_HOST = '192.168.99.100'
var docker = new Docker({
	protocol: 'https',
	host: DOCKER_HOST,
	port: 2376,
	ca: fs.readFileSync(process.env.DOCKER_CERT_PATH + '/ca.pem'),
	cert: fs.readFileSync(process.env.DOCKER_CERT_PATH + '/cert.pem'),
	key: fs.readFileSync(process.env.DOCKER_CERT_PATH + '/key.pem')
})

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
          docker.getContainer(item.Id).kill(function(err){
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


    it('should start node ', function(done) {
        docker.createContainer({Image: 'couchbase-watson', name: "db1"}, function(err, container){
            if(err){done(err)}
            var startOps = {"PortBindings": {"8091/tcp": [{"HostPort": "8091"}]}}
            container.start(startOps, done)
        })
    })

    it('couchbase is running on http://'+DOCKER_HOST+":8091", function(done){
        docker.run('martin/wait',
                   ["-p", "8091"],
                   null,
                   {Links:["db1:db1"]}, done)
    })

})

describe("Provision Cluster", function(){
    this.timeout(60000) // 1 min

    beforeEach(function(){
        logStream = fs.createWriteStream('log.txt', {flags: 'a'});
     })

    it('init node', function(done){
        docker.run('couchbase-cli',
                   ['./couchbase-cli', 'node-init', '-c', 'db1', '-u', 'Administrator', '-p', 'password'],
                   [logStream, process.stderr],
                   {Tty:false, Links:['db1:db1']}, done)
    })



    it('init cluster', function(done){
        docker.run('couchbase-cli',
           ['./couchbase-cli', 'cluster-init', '-c', 'db1', '-u', 'Administrator', '-p', 'password', '--cluster-username', 'Administrator', '--cluster-password', 'password', '--cluster-port', '8091', '--cluster-ramsize', '876', '--services', 'data'],
           [logStream, process.stderr],
           {Tty:false, Links:['db1:db1']}, done)
    })


    it('create bucket', function(done){
        docker.run('couchbase-cli',
           ['./couchbase-cli', 'bucket-create', '-c', 'db1', '-u', 'Administrator', '-p', 'password', '--bucket', 'bucket-1', '--bucket-ramsize', '512', '--bucket-type', 'couchbase', '--wait'],
           [logStream, process.stderr],
           {Tty:false, Links:['db1:db1']}, done)
    })

})

describe("Phase 1: Start data loading", function(){

    it('should start gideon kv clients', function(done){
        docker.createContainer({Image: 'gideon', Links:['db1:db1']}, function(err, container){
            if(err){done(err)}
            container.start(done)
        })
    })

    it('should run for 5 mins', function(done){
        this.timeout(0)
        setTimeout(done, 300000)
    })
})

describe("Teardown", function(){
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

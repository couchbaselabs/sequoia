var Docker = require('dockerode')
	, _ = require('lodash')
    , async = require('async')
    , fs = require('fs')
    , assert = require('assert')
    , yaml = require('js-yaml')
    , commandLineArgs = require('command-line-args');

var SCOPE = null
var TEST = null
var logStream = null
var docker = null

function reloadLogStream(){
	logStream = fs.createWriteStream('log.txt', {flags: 'a'});
}

// opt parser
var cli = commandLineArgs([
  {name: 'scope', alias: 's', type: String},
  {name: 'test', alias: 't', type: String},
])

var options = cli.parse()
if(!options.scope){
	console.log("ERROR: missing -s <scope_file>")
	process.exit(1)
}
if(!options.test){
	console.log("ERROR: missing -t <test_file>")
	process.exit(1)	
}

// get test spec
try {
  SCOPE = yaml.safeLoad(fs.readFileSync(options.scope))
} catch (e) {
  console.log(e)
  process.exit(1)
}

try {
  TEST = yaml.safeLoad(fs.readFileSync(options.test))
} catch (e) {
  console.log(e)
  process.exit(1)
}

// setup docker endpoint
var dockerSpec = SCOPE.docker
var DOCKER_HOST = dockerSpec.host
if(dockerSpec.proto == 'https'){
	var docker = new Docker({
		protocol: dockerSpec.proto,
		host: DOCKER_HOST,
		port: dockerSpec.port,
		ca: fs.readFileSync(process.env.DOCKER_CERT_PATH + '/ca.pem'),
		cert: fs.readFileSync(process.env.DOCKER_CERT_PATH + '/cert.pem'),
		key: fs.readFileSync(process.env.DOCKER_CERT_PATH + '/key.pem')
	})
} else if (dockerSpec.proto == 'unix') {
	// sock path
} else {
	docker = new Docker({host: dockerSpec.host, port: dockerSpec.port})
}

// extrapolate server spec
var servers = {}
_.keys(SCOPE.servers).forEach(function(name){
	servers[name] = []
	var count = SCOPE.servers[name].count || 1
	if(count == 1){
		servers[name].push(name)
	} else {
		for( var i = 1; i<=count;i++){
			servers[name].push(name+"-"+i)
		}
	}
})

// extrapolate bucket spec
var buckets = {}
_.keys(SCOPE.buckets).forEach(function(name){
	buckets[name] = []
	var count = SCOPE.buckets[name].count || 1
	if(count == 1){
		buckets[name].push(name)
	} else {
		for( var i = 1; i<=count;i++){
			buckets[name].push(name+"-"+i)
		}
	}
})

function teardown(){
	describe("removing app containers", function(){
    this.timeout(60000)
    var _glb = {containers: []}

    before(function(done) {
        docker.listContainers({all:true}, function(err, containers){
            _glb.containers = containers
            done()
        })
    });

    it('should stop running containers', function (done) {
        async.eachSeries(_glb.containers, function(item, cb){
          docker.getContainer(item.Id).kill(function(err){
            // ignore kill err as may not be running
            cb()
          })
        }, done)
    })
    it('should remove all containers', function (done) {
        async.eachSeries(_glb.containers, function(item, cb){
            docker.getContainer(item.Id).remove(cb)
        }, done)
    })

	})
}

describe("Teardown", function(){
	teardown()
})

describe("Start Cluster", function(){

	var i = 0
    _.keys(servers).forEach(function(type){
    	servers[type].forEach(function(name){

	        it('should start node ['+name+']', function(done) {
	            docker.createContainer({Image: 'couchbase-watson', name: name}, function(err, container){
	                if(err){done(err)}
	                i++
	                var startOps = {"PortBindings": {"8091/tcp": [{"HostPort": "809"+i}]}}
	                container.start(startOps, done)
	            })
	        })

	    })
    })
    _.keys(servers).forEach(function(type, i){
	    servers[type].forEach(function(name, i){
	        it('verified started node ['+name+']', function(done){
	            i++
	            docker.run('martin/wait',
	                       ["-p", "809"+i],
	                       null,
	                       {Links:[name+":"+name]}, done)
	        })
	    })
	})
})


describe("Provision Cluster", function(){
    this.timeout(60000) // 1 min
    var netMap = {}
    before(function(done) {
        docker.listContainers(function(err, containers){
            async.eachSeries(containers, function(item, cb){ docker.getContainer(item.Id).inspect(function(e,d){
                if(d.Config.Image == "couchbase-watson"){
                	var name = d.Name.slice(1)
                	netMap[name] = d.NetworkSettings.IPAddress
                }
                cb(e)
            }) }, done)
        })
    })

    beforeEach(function(){
    	reloadLogStream()
    })


    it('init nodes', function(done){
        async.eachSeries(_.keys(servers), function(type, type_cb){
        	var rest_username = SCOPE.servers[type].rest_username
        	var rest_password = SCOPE.servers[type].rest_password
        	var rest_port = SCOPE.servers[type].rest_port
	        async.eachSeries(servers[type], function(name, cb){
	        	var ip = netMap[name]+":"+rest_port
	            docker.run('couchbase-cli',
	                       ['./couchbase-cli', 'node-init', '-c', ip, '-u', rest_username, '-p', rest_password],
	                       [logStream, process.stderr],
	                       {Tty:false}, cb)
	        }, type_cb)
        }, done)
    })

    it('init cluster', function(done){
    	//  cluster-init:
    	//     a cluster is initialized when server spec
    	//     is defined that is not joining another server
    	
        async.eachSeries(_.keys(servers), function(type, cb){
		reloadLogStream()

	    	var orchestratorType = type
	    	var clusterSpec = SCOPE.servers[orchestratorType]
	    	if(clusterSpec.join){
	    		cb(null) // done, this cluster is joining another
	    	} else {
		    	var firstNode = servers[orchestratorType][0]
		    	var rest_username = clusterSpec.rest_username
		    	var rest_password = clusterSpec.rest_password
		    	var rest_port = clusterSpec.rest_port.toString()
		    	var services = clusterSpec.services
		    	var ram = clusterSpec.ram.toString()
		    	var orchestratorIp = netMap[firstNode]
		        docker.run('couchbase-cli',
		           ['./couchbase-cli', 'cluster-init',
		            '-c', orchestratorIp, '-u', rest_username, '-p', rest_password,
		            '--cluster-username', rest_username, '--cluster-password', rest_password,
		            '--cluster-port', rest_port, '--cluster-ramsize', ram, '--services', services],
		           [logStream, process.stderr],
		           {Tty:false}, cb)
	    	}
        }, done)

    })


    it('add nodes', function(done){
    	// form clusters based on spec
    	async.eachSeries(_.keys(servers), function(type, type_cb){
			reloadLogStream()
			var orchestratorType = type
	    	var clusterSpec = SCOPE.servers[orchestratorType]
			var n_to_cluster = clusterSpec.cluster
			if(n_to_cluster > servers[type].length){
				n_to_cluster = servers[type].length
			}
			if(n_to_cluster <= 1 && !clusterSpec.join){
				// only 1 node here and not joining elsewhere
				type_cb(null)
				return
			}

			if(clusterSpec.join){
				// override orchestrator to join different server set
				orchestratorType = clusterSpec.join
			}

	    	var firstNode = servers[orchestratorType][0]
	    	var orchestratorIp = netMap[firstNode]
			var rest_username = clusterSpec.rest_username
			var rest_password = clusterSpec.rest_password
			var rest_port = clusterSpec.rest_port

			// add nodes
			var add_nodes = servers[type].slice(0, n_to_cluster)
	        async.eachSeries(add_nodes, function(name, cb){
				reloadLogStream()
	        	var ip = netMap[name]
	        	if(orchestratorIp == ip){
	        		cb(null) // not adding self
	        	} else {
		        	// adding node
		        	ip = ip+":"+rest_port
		            docker.run('couchbase-cli',
		                       ['./couchbase-cli', 'server-add', '-c', orchestratorIp,
		                        '-u', rest_username, '-p', rest_password, '--server-add', ip,
		                        '--server-add-username', rest_username, '--server-add-password', rest_password],
		                       [logStream, process.stderr],
		                       {Tty:false}, cb)
		        }
	            }, type_cb)
	    }, done)
    })

    it('rebalance cluster', function(done){
		async.eachSeries(_.keys(servers), function(type, cb){
			reloadLogStream()

	    	var orchestratorType = type
	    	var clusterSpec = SCOPE.servers[orchestratorType]
	    	if(clusterSpec.join || clusterSpec.cluster <= 1){
	    		cb(null) // done, this cluster is joining another
	    		         // or no rebalance is needed
	    	} else if(clusterSpec.cluster > 1) {
		    	var firstNode = servers[orchestratorType][0]
		    	var rest_username = clusterSpec.rest_username
		    	var rest_password = clusterSpec.rest_password
		    	var rest_port = clusterSpec.rest_port.toString()
		    	var orchestratorIp = netMap[firstNode]+":"+rest_port
		        docker.run('couchbase-cli',
	               ['./couchbase-cli', 'rebalance', '-c', orchestratorIp,
	                '-u', rest_username, '-p', rest_password],
	               [logStream, process.stderr],
	               {Tty:false}, cb)
	    	}
        }, done)
    })

    it('create bucket', function(done){

		async.eachSeries(_.keys(servers), function(type, cb){

	    	var orchestratorType = type
	    	var clusterSpec = SCOPE.servers[orchestratorType]
	    	if(clusterSpec.join){
	    		cb(null) //no buckets for these servers
	    	} else if(clusterSpec.buckets) {
		    	var firstNode = servers[orchestratorType][0]
		    	var rest_username = clusterSpec.rest_username
		    	var rest_password = clusterSpec.rest_password
		    	var rest_port = clusterSpec.rest_port.toString()
		    	var orchestratorIp = netMap[firstNode]+":"+rest_port

		    	var bucketType = clusterSpec.buckets
		    	var bucketSpec = SCOPE.buckets[bucketType]
		    	var clusterBuckets = buckets[bucketType]
		    	async.eachSeries(clusterBuckets, function(name, bucket_cb){
					reloadLogStream()

		    		var ram = bucketSpec.ram.toString()
		    		var replica = bucketSpec.replica.toString() //TODO
		    		var bucketSpecType = bucketSpec.type
	        		docker.run('couchbase-cli',
			           ['./couchbase-cli', 'bucket-create',
			           '-c', orchestratorIp, '-u', rest_username, '-p', rest_password,
			           '--bucket', name, '--bucket-ramsize', ram,
			           '--bucket-type', bucketSpecType, '--wait'],
			           [logStream, process.stderr],
			           {Tty:false}, bucket_cb)
		    	}, cb)
	    	}
        }, done)


    })
})



describe("Test", function(){
    var links = {pairs: []}

    async.eachSeries(_.keys(TEST), function(phase, phase_cb){

        describe("Phase: "+phase, function(){
            before(function(done) {
                links['pairs'] = _
                    .chain(servers)
                        .values()
                        .flatten()
                        .map(function(v){ return v+':'+v})
                            .value()
                done()
            })

            // generate tests
            var phaseTests = _.filter(_.keys(TEST[phase]), function(i){
            	return TEST[phase][i].test
            })
            var phaseDuration = _.find(TEST[phase], 'duration') || 30000
        	if(phaseDuration){
        		lastPhaseDuration = phaseDuration.duration
        	}
            async.each(phaseTests, function(test, test_cb){
                var testSpec = TEST[phase][test].test
                var framework = testSpec.framework
                var wait = testSpec.duration || 0
                it('test: '+framework, function(done){
                    if (framework){
                        // start docker framework
                        if(testSpec.async){
                            docker.createContainer({
                                Image: framework,
                                Links:links.pairs},
                                function(err, container){
                                    if(err){done(err)}
                                    container.start(done)
                                })
                        } else {
                            docker.run(framework, null,
                              [logStream, process.stderr],
                              {Tty:false, Links: links.pairs}, done)
                        }
                    } else {
                        done()
                    }
                })
	  			test_cb()
            }, phase_cb) // todo drop in promises for yet to complete tasks
        })

    })
})


describe("Teardown", function(){
 	teardown()
})


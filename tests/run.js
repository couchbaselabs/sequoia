var Docker = require('dockerode')
	, _ = require('lodash')
    , async = require('async')
    , fs = require('fs')
    , assert = require('assert')
    , yaml = require('js-yaml')
	, Promise = require('promise')
    , commandLineArgs = require('command-line-args');

var client = require("./lib/client.js").api
    , util = require("./lib/util.js").api
    , argResolver = require("./lib/resolve.js").api.resolve

var logStream = null

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

var SCOPE = util.loadSpec(options.scope)
var TEST = util.loadSpec(options.test)

var docker = client.init(SCOPE.docker)
var buckets = util.extrapolateRange(SCOPE.buckets)
var servers = util.extrapolateRange(SCOPE.servers)

function teardown(){
	describe("removing app containers", function(){
    	this.timeout(60000)

	    before(function(done) {
	    	client.setContainers({all:true})
	    		.then(done)
	    });
	    it('should stop running containers', function () {
	    	return client.killContainers()
	    })
	    it('should remove all containers', function () {
	    	return client.removeContainers()
	    })

	})
}


describe("Teardown", function(){
	teardown()
})

describe("Create Network", function(){
	var networkSpec = SCOPE.docker.network
	if(networkSpec){
		it('should create network: '+ networkSpec.name, function(){
			var network = {
			  "Name": networkSpec.name,
			  "Driver": networkSpec.driver,
			  "IPAM":{
			    "Config":[{
			      "Subnet":networkSpec.subnet
			    }]
			  }
			}
			return client.createNetwork(network)
		})
	}
})

describe("Start Cluster", function(){
    var netMap = {}

	util.values(servers)
		.forEach(function(name, i){
	        it('should start node ['+name+']', function() {
	        	var network = client.getNetwork()
    		 	var remotePort = 8091+i
	        	return client.runContainer(false,
	        		{Image: 'couchbase-watson',
	        		 name: name,
	        		 HostConfig: {
	        		 	PortBindings: {"8091/tcp": [{"HostPort": remotePort.toString()}]},
                                        NetworkMode: network
	        		 }}
	        	)
	        })
	    })

	it('update ip addresses', function(){
		// save addresses for node containers
		return client.updateContainerIps()
    		.then(function(){
    			netMap = client.getContainerIps("couchbase-watson")
    		})
	})
	util.values(servers)
		.forEach(function(name){
	        it('verified started node ['+name+']', function(){
                var ip = netMap[name]
	        	return client.runContainer(true,
	        		{Image: 'martin/wait',
	        		 HostConfig: { NetworkMode: client.getNetwork(), 
		    	 				   Links:[name+":"+name]
	        		 },
	        		 Cmd: ["-c", ip+":8091", "-t", "120"]}
	        	)
	        })
	    })
	
})


describe("Provision Cluster", function(){
    this.timeout(60000) // 1 min
    var netMap = {}

    before(function() {
    	// save addresses for node containers
    	return client.updateContainerIps()
	    		.then(function(){
	    			netMap = client.getContainerIps("couchbase-watson")
	    		})
    })

    beforeEach(function(){
    	reloadLogStream()
    })

    it('init nodes', function(){
    	var serverTypes = util.keys(servers)
    	var promises = []
        serverTypes.forEach(function(type){
        	var rest_username = SCOPE.servers[type].rest_username
        	var rest_password = SCOPE.servers[type].rest_password
        	var rest_port = SCOPE.servers[type].rest_port

	        servers[type].forEach(function(name){
	        	var ip = netMap[name]+":"+rest_port
	        	  var p = client.runContainer(true,{
	        	 		Image: 'couchbase-cli',
				 		HostConfig: {NetworkMode: client.getNetwork(), 
		    	 					Links:[name+":"+name]},
	        		 	Cmd: ['./couchbase-cli', 'node-init', '-c', name,
	        		       	  '-u', rest_username, '-p', rest_password]
	        		})
	        	  promises.push(p)
	        })
        })
        return Promise.all(promises)
    })

    it('init cluster', function(){
    	//  cluster-init:
    	//     initializes a set of servers within clusters
    	var serverTypes = util.keys(servers)
    	var promises = []
        serverTypes.forEach(function(type){

        	// set first node to be orchestrator
	    	var orchestratorType = type
	    	var clusterSpec = SCOPE.servers[orchestratorType]
	    	var firstNode = servers[orchestratorType][0]

	    	// provision vars
	    	var rest_username = clusterSpec.rest_username
	    	var rest_password = clusterSpec.rest_password
	    	var rest_port = clusterSpec.rest_port.toString()
	    	var services = clusterSpec.services
	    	var ram = clusterSpec.ram.toString()

			servers[type].forEach(function(name){
				var ip = netMap[name]+":"+rest_port
				var command = ['./couchbase-cli', 'cluster-init',
					    '-c', name, '-u', rest_username, '-p', rest_password,
					    '--cluster-username', rest_username, '--cluster-password', rest_password,
					    '--cluster-port', rest_port, '--cluster-ramsize', ram, '--services', services]
				    if(clusterSpec.index_ram){
					command = command.concat(['--cluster-index-ramsize', clusterSpec.index_ram.toString()])
				    }

					var p = client.runContainer(true,{
						Image: 'couchbase-cli',
					HostConfig: {NetworkMode: client.getNetwork(), 
			    	 					Links:[name+":"+name]},
						Cmd: command
					})
					  promises.push(p)
			})

        })
  		return Promise.all(promises)

    })

    it('add nodes', function(done){
    	// form clusters based on spec
    	var serverTypes = util.keys(servers)
    	var promises = []
	    async.eachSeries(serverTypes, function(type, type_cb){
			var orchestratorType = type
	    	var clusterSpec = SCOPE.servers[orchestratorType]
			var n_to_cluster = clusterSpec.init_nodes
			if(n_to_cluster > servers[type].length){
				n_to_cluster = servers[type].length
			}
			if(n_to_cluster <= 1){
				// skip, only 1 node in this cluster
				type_cb(null)
				return
			}

	    	var firstNode = servers[orchestratorType][0]
	    	var orchestratorIp = netMap[firstNode]
			var rest_username = clusterSpec.rest_username
			var rest_password = clusterSpec.rest_password
			var rest_port = clusterSpec.rest_port

			// add nodes
			var add_nodes = servers[type].slice(0, n_to_cluster)
	        async.eachSeries(add_nodes, function(name, cb){
	        	var ip = netMap[name]
	        	if(orchestratorIp == ip){
	        		cb(null) // not adding self
	        	} else {
		        	// adding node
		        	ip = ip+":"+rest_port
		        	var hostConfig = 
					client.runContainer(true,{
		    	 		HostConfig: {NetworkMode: client.getNetwork(), 
		    	 					 Links:[name+":"+name]
},
						Image: 'couchbase-cli',
					 	Cmd: ['./couchbase-cli', 'server-add', '-c', orchestratorIp,
	                          '-u', rest_username, '-p', rest_password, '--server-add', name,
			                  '--server-add-username', rest_username, '--server-add-password', rest_password]
				        }).then(cb).catch(cb)
		        }
            }, type_cb)
	    }, done)
    })


    it('rebalance cluster', function(){
    	var serverTypes = util.keys(servers)
    	var promises = []
		serverTypes.forEach(function(type){

	    	var orchestratorType = type
	    	var clusterSpec = SCOPE.servers[orchestratorType]
	    	if(clusterSpec.init_nodes <= 1){
	    		return // skip, rebalance is needed for single node cluster
	    	} else if(clusterSpec.init_nodes > 1) {
		    	var firstNode = servers[orchestratorType][0]
		    	var rest_username = clusterSpec.rest_username
		    	var rest_password = clusterSpec.rest_password
		    	var rest_port = clusterSpec.rest_port.toString()
		    	var orchestratorIp = netMap[firstNode]+":"+rest_port
		    	var p = client.runContainer(true,{
						Image: 'couchbase-cli',
		    	 		HostConfig: 
		    	 			{NetworkMode: client.getNetwork(), 
		    	 					Links:[firstNode+":"+firstNode]},
					 		Cmd: ['./couchbase-cli', 'rebalance', '-c', firstNode,
	                				'-u', rest_username, '-p', rest_password]
				        })
		    	promises.push(p)
	    	}
        })

        return Promise.all(promises)
    })

    it('create buckets', function(done){

    	var serverTypes = util.keys(servers)
		async.eachSeries(serverTypes, function(type, cb){

	    	var orchestratorType = type
	    	var clusterSpec = SCOPE.servers[orchestratorType]
	    	if(!clusterSpec.buckets){
	    		cb(null) // skip, no buckets for these servers now
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
		    		client.runContainer(true,{
						Image: 'couchbase-cli',
		    	 		HostConfig: {NetworkMode: client.getNetwork(), 
		    	 					Links:[firstNode+":"+firstNode]},
					 	Cmd: ['./couchbase-cli', 'bucket-create',
			           '-c', orchestratorIp, '-u', rest_username, '-p', rest_password,
			           '--bucket', name, '--bucket-ramsize', ram,
			           '--bucket-type', bucketSpecType, '--wait']
				        }).then(bucket_cb).catch(bucket_cb)
		    	}, cb)
	    	}
        }, done)


    })

})


describe("Test", function(){
    var links = {pairs: []}
	var phases = util.keys(TEST)

	// run each phase
    async.eachSeries(phases, function(phase, cb){

        describe("Phase: "+phase, function(done){

            before(function() {
                links['pairs'] = util.containerLinks(servers)
                return client.updateContainerIps()
            })

            // generate tasks
            var phaseTests = _.filter(TEST[phase], 'test')

        	// run each test in the phase
           async.each(phaseTests, function(t){
           		var testSpec = t.test
           		var scale = testSpec.scale || 1
                var container = testSpec.container
                var duration = testSpec.duration || 0
                var command = testSpec.command
                if(testSpec.servers){
                	// translate link pairs
                	var startEnd = testSpec.servers.split(":")
                		.map(function(i){return parseInt(i)})
                	var links = util.containerLinks(servers)
                	var range = startEnd[1] - startEnd[0]+1
                	links.pairs = links.slice(0, range)
                					.map(function(l, i){
                						i++
                						var ii = startEnd[0]+i
                						return l.replace(i, ii)
                					})
                }
                if(command){
                	it('resolve command: '+command, function(){
	                	command = _.map(command.split(/\s+/),
	                		function(arg){
	                			var argv = arg.split(":")
	                			if(argv.length > 1){
	                				var subscope = SCOPE[argv[0]]
	                				var func = argv[1]
	                				var fargs = argv.slice(2)
	                				var val = argResolver(subscope,
	                					                  func,
	                					                  fargs,
	                					                  client.getContainerIps('couchbase-watson'))
	                				argv = val
	                			} else {
	                				argv = arg
	                			}
	                			return argv
	                		})
	                })

                }
                for (var i = 0; i<scale; i++){
	                it('test: '+container, function(){
	                    if (container){
	                    	var network = client.getNetwork()
	                    	var hostConfig = {NetworkMode: network}
	                    	if (network == "bridge" && links){
	                    		hostConfig["Links"] = links.pairs
			                }
	                    	return client.runContainer(testSpec.wait,
	                    		{
									Image: container,
									Cmd: command,
									HostConfig: hostConfig
								}, null, duration)
	                    } else {
	                        // something else
	                    }
	                })
	            }
            })
           cb()
        })

    })
})


describe("Teardown", function(){
//	teardown()
})


var Docker = require('dockerode')
	, _ = require('lodash')
    , async = require('async')
    , fs = require('fs')
    , assert = require('assert')
    , yaml = require('js-yaml')
	, Promise = require('promise')
    , commandLineArgs = require('command-line-args');

var client = require("./lib/client.js").api
    util = require("./lib/util.js").api

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
var servers = util.extrapolateRange(SCOPE.servers)
var buckets = util.extrapolateRange(SCOPE.buckets)


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


describe("Start Cluster", function(){

	util.values(servers)
		.forEach(function(name, i){
	        it('should start node ['+name+']', function() {
	        	return client.runContainer(false,
	        		{Image: 'couchbase-watson', name: name},
	        		{"PortBindings": {"8091/tcp": [{"HostPort": "809"+(i+1)}]}}
	        	)
	        })
	    })

	util.values(servers)
		.forEach(function(name, i){
	        it('verified started node ['+name+']', function(){
	        	return client.runContainer(true,
	        		{Image: 'martin/wait', Cmd: ["-p", "809"+(i+1)]},
	        		{Links:[name+":"+name]}
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
	        		 Cmd: ['./couchbase-cli', 'node-init', '-c', ip,
	        		       '-u', rest_username, '-p', rest_password]
	        		})
	        	  promises.push(p)
	        })
        })
        return Promise.all(promises)
    })
    it('init cluster', function(){
    	//  cluster-init:
    	//     a cluster is initialized when server spec
    	//     is defined that is not joining another server
    	var serverTypes = util.keys(servers)
    	var promises = []
        serverTypes.forEach(function(type){

	    	var orchestratorType = type
	    	var clusterSpec = SCOPE.servers[orchestratorType]
	    	if(clusterSpec.join){
	    		return // skip, this cluster is joining another
	    	} else {
		    	var firstNode = servers[orchestratorType][0]
		    	var rest_username = clusterSpec.rest_username
		    	var rest_password = clusterSpec.rest_password
		    	var rest_port = clusterSpec.rest_port.toString()
		    	var services = clusterSpec.services
		    	var ram = clusterSpec.ram.toString()
		    	var orchestratorIp = netMap[firstNode]
				var p = client.runContainer(true,{
					Image: 'couchbase-cli',
				 	Cmd: ['./couchbase-cli', 'cluster-init',
			            '-c', orchestratorIp, '-u', rest_username, '-p', rest_password,
			            '--cluster-username', rest_username, '--cluster-password', rest_password,
			            '--cluster-port', rest_port, '--cluster-ramsize', ram, '--services', services]
			        })
        		promises.push(p)
	    	}
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
	        	var ip = netMap[name]
	        	if(orchestratorIp == ip){
	        		cb(null) // not adding self
	        	} else {
		        	// adding node
		        	ip = ip+":"+rest_port
					client.runContainer(true,{
						Image: 'couchbase-cli',
					 	Cmd: ['./couchbase-cli', 'server-add', '-c', orchestratorIp,
	                          '-u', rest_username, '-p', rest_password, '--server-add', ip,
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
	    	if(clusterSpec.join || clusterSpec.cluster <= 1){
	    		return // skip, this cluster is joining another
	    		       // or no rebalance is needed
	    	} else if(clusterSpec.cluster > 1) {
		    	var firstNode = servers[orchestratorType][0]
		    	var rest_username = clusterSpec.rest_username
		    	var rest_password = clusterSpec.rest_password
		    	var rest_port = clusterSpec.rest_port.toString()
		    	var orchestratorIp = netMap[firstNode]+":"+rest_port
		    	var p = client.runContainer(true,{
						Image: 'couchbase-cli',
					 	Cmd: ['./couchbase-cli', 'rebalance', '-c', orchestratorIp,
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
	    	if(clusterSpec.join){
	    		cb(null) // skip, no buckets for these servers
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
            })

            // generate tests
            var phaseTests = _.filter(TEST[phase], 'test')

        	// run each test in the phase
           async.each(phaseTests, function(val){
           		var testSpec = val.test
                var framework = testSpec.framework
                var duration = testSpec.duration || 0
                it('test: '+framework, function(){
                    if (framework){
                    	return client.runContainer(testSpec.async,
                    		{
								Image: framework,
							 	Links:links.pairs
							}, null, duration)
                    } else {
                        // something else
                    }
                })
            })
           cb()
        })

    })
})


describe("Teardown", function(){
 	teardown()
})


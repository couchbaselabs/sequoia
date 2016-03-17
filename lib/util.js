var _ = require('lodash')
    , fs = require('fs')
    , yaml = require('js-yaml')

exports.api = (function(){
	var docker = null

    return {
        loadSpec: function(filePath){
			try {
			  return yaml.safeLoad(fs.readFileSync(filePath))
			} catch (e) {
			  console.log(e)
			  process.exit(1)
			}
        },
        readHostFile: function(filePath){
            // reads in a hostfile which is a text file with a hostname/ips
            // on each line.
            // returns array of hostname/ips
			try {
                var hostFileData = fs.readFileSync(filePath,'utf8')
                return hostFileData.split("\n").filter(function(h){
                    return h.trim().length > 1
                })
			} catch (e) {
			  console.log(e)
			  process.exit(1)
			}
        },
        extrapolateRange:  function(spec){
        	// When given a directive which is intended to scale
        	// ie: {buckets: name, count: 10}
        	// extrapolate's -> [bucket-1, bucket-2, ... bucket-10]
        	var range = {}
        	_.keys(spec).forEach(function(name){
				range[name] = []
				var count = spec[name].count || 1
				if(count == 1){
					range[name].push(name)
				} else {
					for( var i = 1; i<=count;i++){
                        var parts = name.split(".")
                        var fqn = name.split(".")[0]+"-"+i
                        if (parts.length > 1){
                           fqn = fqn+"."+parts.slice(1).join(".")
                        }
						range[name].push(fqn)
					}
				}
			})
			return range
        },
        values: function(obj){
        	// compute values of an object and then flattens
        	//    -> { db: [ 'db-1', 'db-2', 'db-3' ], dbx: [ 'dbx-1', 'dbx-2' ] }
        	//    <- [ 'db-1', 'db-2', 'db-3', 'dbx-1', 'dbx-2' ]
        	return _.flatten(_.values(obj))
        },
        keys: function(obj){
        	return _.keys(obj)
        },
        containerLinks: function(obj){
        	// forms container link args from input
        	//   -> { db: [ 'db-1', 'db-2', 'db-3' ], dbx: [ 'dbx-1', 'dbx-2' ] }
        	//   <- [db-1:db-1, db-2:db-2....]
            return _
            	.chain(obj)
	                .values()
	                .flatten()
	                .map(function(v){ return v+':'+v})
	                    .value()
        },
        mapHostsToScope: function(hostFileData, servers){
            var i = 0
            var scopeMapping = {}
            for (var key in servers){
                scopeHosts = servers[key]
                scopeHosts.forEach(function(h){
                    if(i<hostFileData.length){
                        scopeMapping[h] = hostFileData[i]
                        i++
                    }
                })
            }
            return scopeMapping
        },
        mapHostsToServices: function(serviceSpec, numNodes){
            var numIndexNodes = serviceSpec.index || 0
            var numQueryNodes = serviceSpec.query || 0
            var numDataNodes = serviceSpec.data
            var strategy = serviceSpec.strategy || "spread"
            var serviceList = []

            // Spread Strategy
//            var indexStartPos = numNodes - 
            var queryStartPos = numDataNodes 
            for (var i = 0; i < numNodes; i++){
                // make first set of nodes data
                // and second set query to avoid
                // overlapping if possible when specific
                // number of service types provided
                var services = []
                if(numDataNodes > 0){
                    services.push("data")
                    numDataNodes--
                }
                if(numIndexNodes > 0){
                    if(numDataNodes == 0){
                        // found a free node
                        services.push("index")
                        numIndexNodes--
                    } else if (i >= (numNodes-numIndexNodes)) {
                        // have to meet required # of index nodes
                        services.push("index")
                        numIndexNodes--
                    }
                }
                if(numQueryNodes > 0 && (i >= (numNodes-numQueryNodes))){
                    services.push("query")
                    numQueryNodes--
                }
                services = services.join(",")
                serviceList.push(services)
            }
            return serviceList
        }
    }
})()

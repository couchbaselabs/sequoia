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
                                                if (parts.length > 0){
                                                   fqn = fqn+"."+parts.slice(1).join(".")
                                                }
                                                console.log(fqn) 
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
        }
    }
})()

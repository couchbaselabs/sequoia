var Docker = require('dockerode')
    , Promise = require('promise')
    , async = require('async')
    , fs = require('fs')


exports.api = (function(){
	var docker = null
	var containerIps = {}
	var locals = {
		containers: []
	}

	function createContainer(createOpts){
		return _as_promised(function(done){
			docker.createContainer(createOpts, function(err, container){
				done({_data: container, err:err})
			})
		})
	}
	function startContainer(container, startOpts){
		return _as_promised(function(done){
			container.start(startOpts, done)
		})
	}
	function waitForContainer(container){ // TODO: optional timeout

		// attach and log container output
	    container.attach({stream: true, stdout: true, stderr: true}, function (err, stream) {
		    stream.pipe(logger())
		});

		return _as_promised(function(done){
			container.wait(function(err, rc){
				if(rc.StatusCode == 0){
					done()
				}
				else {
					var err = new Error("failed - see log.txt")
					done(err)
				}
			})

		})
	}

    return {
        init: function(dockerSpec){
        	// setup docker endpoint
			var DOCKER_HOST = dockerSpec.host
			if(dockerSpec.proto == 'https'){
				docker = new Docker({
					protocol: dockerSpec.proto,
					host: DOCKER_HOST,
					port: dockerSpec.port,
					ca: fs.readFileSync(process.env.DOCKER_CERT_PATH + '/ca.pem'),
					cert: fs.readFileSync(process.env.DOCKER_CERT_PATH + '/cert.pem'),
					key: fs.readFileSync(process.env.DOCKER_CERT_PATH + '/key.pem')
				})
			} else if (dockerSpec.proto == 'unix') {
				// sock path
				docker = new Docker({socketPath: '/var/run/docker.sock'})
			} else {
				docker = new Docker({host: dockerSpec.host, port: dockerSpec.port})
			}
			return docker
        },
		setContainers: function(){
			return _as_promised(function(done){
				docker.listContainers({all:true}, function(err, containers){
		            locals.containers = containers
					done(err)
				})
			})
		},
		killContainers: function(){
			return _as_promised(function(done){
		        async.eachSeries(locals.containers, function(item, cb){
		          if(item.Image == "swarm"){ cb() }
		          	else{
		          docker.getContainer(item.Id).kill(function(err){
		          	cb() // ignore kill err
		          })
		      }
		        }, done)
		    })
		},
		removeContainers: function(){
			return _as_promised(function(done){
		        async.eachSeries(locals.containers, function(item, cb){
		          if (item.Image == "swarm"){
		          	cb()
		          } else {
			          docker.getContainer(item.Id).remove({force: true}, cb)
			      }
		        }, done)
		    })
		},
		runContainer: function(wait, createOpts, startOpts, duration){
			duration = duration || 1000

			return _as_promised(function(done){

				// create container
				createContainer(createOpts).catch(done)
					.then(function(container){

						// start container
						startContainer(container, startOpts).catch(done)
							.then(function(){

								// wait for finish if necessary
								if(wait){
									waitForContainer(container).catch(done)
										.then(done)
								} else {
									// can finish as long as duration is complete
									setTimeout(done, duration)
								}
							})
					})
			})
		},
		updateContainerIps: function(network){
			return _as_promised(function(done){
		        docker.listContainers(function(err, containers){
		            async.eachSeries(containers, function(item, cb){ docker.getContainer(item.Id).inspect(function(e,d){
		            	var image = d.Config.Image
		            	var name = d.Name.slice(1)
		            	if(!containerIps[image]){
		            		containerIps[image] = {}
		            	}
		            	var netSettings = d.NetworkSettings
		            	if(network){
			            	containerIps[image][name] = netSettings.Networks[network].IPAddress
		            	} else {
			            	containerIps[image][name] = netSettings.IPAddress
			            }
		                cb(e)
		            }) }, done)
		        })
			})
		},
		getContainerIps: function(_type){
			if(_type){
				return containerIps[_type]
			} else {
				// return everything
				return containerIps
			}
		}
    }
})()

function logger(){
	return fs.createWriteStream('log.txt', {flags: 'a'});
}

// promise wrapper for callback functions
function _as_promised(func){
	return new Promise(function (resolve, reject){
        func(function(resp){

        	// handle resolve reject
        	if(resp){
        		if(resp._data && !resp.err){
	        		// response has data without err
        			resolve(resp._data)
        		} else {
        			// resp doesn't not have data 'or' has err
        			reject(resp)
        		}
        	} else {
        		// resp was null - ok
        		resolve()
        	}
        })
    })
}
